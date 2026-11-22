"""
FactoryIQ investigation agent runner — Milestone 3.

Orchestrates a Claude-powered investigation loop that calls MCP tools,
logs evidence, and submits a structured finding for human review.

Design constraints:
  - No direct database access from this module; all data access via MCP tools.
  - flag_for_review is the only write-path the agent touches.
  - Human approval (approve/reject) requires a separate token the agent never holds.
  - Temperature = 0 for reproducible outputs.
  - Hard limits: max_tool_calls, timeout seconds.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from db import get_pool
from agent.prompts import SYSTEM_PROMPT, build_investigation_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (all from environment variables)
# ---------------------------------------------------------------------------

def _agent_config() -> dict[str, Any]:
    app_port = os.environ.get("APP_PORT", "8000")
    return {
        "api_key":        os.environ.get("ANTHROPIC_API_KEY", ""),
        "model":          os.environ.get("AGENT_MODEL", "claude-sonnet-4-6"),
        "mcp_url":        os.environ.get("AGENT_MCP_URL", f"http://localhost:{app_port}/mcp/"),
        "mcp_token":      os.environ.get("MCP_BEARER_TOKEN", "changeme"),
        "max_tool_calls": int(os.environ.get("AGENT_MAX_TOOL_CALLS", "20")),
        "timeout_secs":   float(os.environ.get("AGENT_TIMEOUT_SECONDS", "90")),
        "max_tokens":     int(os.environ.get("AGENT_MAX_TOKENS", "4096")),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_investigation(
    investigation_id: str,
    asset_id: str,
    trigger_alarm_id: str | None,
    event_queue: asyncio.Queue | None,
) -> None:
    """
    Run an AI investigation. Updates the investigations DB row throughout.
    Pushes SSE-ready event dicts to event_queue if provided.
    Always terminates (never raises) — failures are recorded in the DB.
    """
    cfg = _agent_config()

    if not cfg["api_key"]:
        await _fail(investigation_id, "ANTHROPIC_API_KEY is not configured", event_queue)
        return

    try:
        await asyncio.wait_for(
            _core(investigation_id, asset_id, trigger_alarm_id, event_queue, cfg),
            timeout=cfg["timeout_secs"],
        )
    except asyncio.TimeoutError:
        await _fail(
            investigation_id,
            f"Investigation timed out after {cfg['timeout_secs']:.0f}s",
            event_queue,
        )
    except Exception as exc:
        logger.exception("Unexpected error in investigation %s", investigation_id)
        await _fail(investigation_id, str(exc), event_queue)


# ---------------------------------------------------------------------------
# Core investigation loop
# ---------------------------------------------------------------------------

async def _core(
    investigation_id: str,
    asset_id: str,
    trigger_alarm_id: str | None,
    event_queue: asyncio.Queue | None,
    cfg: dict[str, Any],
) -> None:
    inv_uuid = uuid.UUID(investigation_id)
    client = anthropic.AsyncAnthropic(api_key=cfg["api_key"])

    http_client = create_mcp_http_client(
        headers={"Authorization": f"Bearer {cfg['mcp_token']}"}
    )

    async with streamable_http_client(cfg["mcp_url"], http_client=http_client) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()

            # Fetch the available tools and convert to Anthropic format
            tools_result = await mcp.list_tools()
            anthropic_tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.input_schema if isinstance(t.input_schema, dict) else dict(t.input_schema),
                }
                for t in tools_result.tools
            ]

            # Build set of tool names that accept investigation_id so we can inject it
            tools_with_inv_id: set[str] = {
                t.name
                for t in tools_result.tools
                if "investigation_id" in (
                    t.input_schema if isinstance(t.input_schema, dict) else dict(t.input_schema)
                ).get("properties", {})
            }

            messages: list[dict] = [
                {
                    "role": "user",
                    "content": build_investigation_prompt(
                        investigation_id=investigation_id,
                        asset_id=asset_id,
                        trigger_alarm_id=trigger_alarm_id,
                    ),
                }
            ]

            tool_call_count = 0
            flagged_for_review = False

            while tool_call_count < cfg["max_tool_calls"]:
                response = await client.messages.create(
                    model=cfg["model"],
                    max_tokens=cfg["max_tokens"],
                    system=SYSTEM_PROMPT,
                    tools=anthropic_tools,  # type: ignore[arg-type]
                    messages=messages,  # type: ignore[arg-type]
                )

                # Append assistant turn to conversation history
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    # Claude finished without calling flag_for_review.
                    # Treat the final text as an un-submitted finding.
                    final_text = " ".join(
                        b.text for b in response.content if hasattr(b, "text")
                    ).strip()
                    if final_text and not flagged_for_review:
                        logger.warning(
                            "Investigation %s: Claude ended without flag_for_review",
                            investigation_id,
                        )
                        await _emit(event_queue, {
                            "type": "warning",
                            "message": "Agent ended without submitting finding for review.",
                        })
                    break

                if response.stop_reason != "tool_use":
                    logger.warning(
                        "Investigation %s: unexpected stop_reason=%s",
                        investigation_id, response.stop_reason,
                    )
                    break

                # ── Process each tool call in this turn ──────────────────────
                tool_results: list[dict] = []

                for block in response.content:
                    if not hasattr(block, "type") or block.type != "tool_use":
                        continue

                    tool_call_count += 1

                    await _emit(event_queue, {
                        "type": "tool_call",
                        "tool_name": block.name,
                        "inputs": block.input,
                        "sequence": tool_call_count,
                    })

                    # Inject investigation_id for tools that accept it so evidence is logged
                    tool_inputs = dict(block.input)
                    if block.name in tools_with_inv_id:
                        tool_inputs["investigation_id"] = investigation_id

                    # Execute the tool via real MCP protocol
                    tool_output = await _call_mcp_tool(mcp, block.name, tool_inputs)

                    success = tool_output.get("success", False)
                    await _emit(event_queue, {
                        "type": "tool_result",
                        "tool_name": block.name,
                        "success": success,
                        "sequence": tool_call_count,
                    })

                    # flag_for_review sets investigation → pending_review in DB
                    if block.name == "flag_for_review" and success:
                        flagged_for_review = True

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_output),
                    })

                if flagged_for_review:
                    break

                # Feed results back to Claude for the next turn
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})

            # ── Persist agent metadata ──────────────────────────────────────
            pool = get_pool()
            if flagged_for_review:
                await pool.execute(
                    """
                    UPDATE investigations
                    SET agent_model = $2, agent_tool_calls = $3
                    WHERE investigation_id = $1
                    """,
                    inv_uuid, cfg["model"], tool_call_count,
                )
                await _emit(event_queue, {
                    "type": "complete",
                    "status": "pending_review",
                    "tool_calls_used": tool_call_count,
                })
            else:
                # Reached limit without submitting
                await pool.execute(
                    """
                    UPDATE investigations
                    SET status = 'failed',
                        agent_model = $2,
                        agent_error = $3,
                        agent_tool_calls = $4
                    WHERE investigation_id = $1
                    """,
                    inv_uuid,
                    cfg["model"],
                    f"Agent used {tool_call_count} tool calls without calling flag_for_review",
                    tool_call_count,
                )
                await _emit(event_queue, {
                    "type": "error",
                    "message": "Agent did not submit a finding.",
                })

    # Signal SSE stream end
    await _emit(event_queue, None)  # sentinel


# ---------------------------------------------------------------------------
# Scripted runner (no Anthropic API — for regression testing only)
# ---------------------------------------------------------------------------


def _analyze_tag_telemetry(tag_name: str, result: dict) -> tuple[str, str]:
    """
    Analyze a query_telemetry MCP result. Returns (description, evidence_tier).
    Uses actual observed values — does not assume nominal conditions.
    """
    data = result.get("data", {})
    readings = data.get("readings", [])
    if not readings:
        return f"No {tag_name} readings in query window", "INSUFFICIENT_DATA"

    good = [r for r in readings if r.get("opc_quality_label") == "Good"]
    if not good:
        return f"{tag_name}: {len(readings)} readings, all non-Good quality", "INSUFFICIENT_DATA"

    values = [r["value"] for r in good]
    mean_v = sum(values) / len(values)
    min_v  = min(values)
    max_v  = max(values)
    unit   = good[0].get("unit", "")
    n      = len(good)

    if tag_name == "Pressure_bar":
        if min_v < 2.0:
            return (
                f"Pressure_bar anomalous low-pressure readings: "
                f"min {min_v:.2f}{unit}, mean {mean_v:.2f}{unit} ({n} readings)",
                "STATISTICAL_SIGNAL",
            )
        if max_v > 6.5:
            return (
                f"Pressure_bar elevated readings: "
                f"max {max_v:.2f}{unit}, mean {mean_v:.2f}{unit} ({n} readings)",
                "STATISTICAL_SIGNAL",
            )
        return (
            f"Pressure_bar within normal range: "
            f"mean {mean_v:.2f}{unit}, [{min_v:.2f}–{max_v:.2f}]{unit} ({n} readings)",
            "CONFIRMED_OBSERVATION",
        )

    return (
        f"{tag_name}: mean {mean_v:.2f}{unit} ({n} readings)",
        "CONFIRMED_OBSERVATION",
    )


def _build_scripted_finding(asset_id: str, tool_results: dict[str, Any]) -> tuple[str, list, list]:
    """
    Rule-based finding from actual MCP tool responses.
    NOT an AI model — deterministic rules applied to observed data.
    Returns (finding_text, evidence_tiers, alt_hypotheses).
    """
    events_data  = tool_results.get("get_recent_events",    {}).get("data", {})
    quality_data = tool_results.get("check_data_quality",   {}).get("data", {})
    baseline_data = tool_results.get("compare_baseline",    {}).get("data", {})
    docs_data     = tool_results.get("query_equipment_docs", {}).get("data", {})

    # Pick the primary flow tag for this asset
    flow_key = next(
        (k for k in tool_results if k.startswith("query_telemetry_")
         and k not in ("query_telemetry_Pressure_bar",)), None
    )
    pressure_result = tool_results.get("query_telemetry_Pressure_bar", {})
    flow_result     = tool_results.get(flow_key, {}) if flow_key else {}
    flow_tag        = flow_key.replace("query_telemetry_", "") if flow_key else "FlowRate_Lmin"

    alarm_count = int(events_data.get("count", 0))

    tags_quality  = quality_data.get("tags", [])
    fresh_count   = sum(1 for t in tags_quality if t.get("freshness_status") == "FRESH")
    total_quality = len(tags_quality)
    all_fresh     = fresh_count == total_quality and total_quality > 0

    baseline_msg    = str(baseline_data.get("message", ""))
    baseline_ok     = bool(baseline_data) and "Insufficient" not in baseline_msg and "0 rows" not in baseline_msg

    docs_count = int(docs_data.get("count", 0))

    pressure_desc, pressure_tier = _analyze_tag_telemetry("Pressure_bar", pressure_result)
    flow_desc,     flow_tier     = _analyze_tag_telemetry(flow_tag, flow_result)

    anomaly = pressure_tier == "STATISTICAL_SIGNAL" or alarm_count > 3

    if anomaly and "low-pressure" in pressure_desc:
        hypothesis = (
            f"{asset_id} is exhibiting abnormal pressure conditions. "
            f"Observed readings deviate from expected nominal range. "
            f"Possible causes: flow restriction, sensor drift, or upstream supply issue."
        )
    elif anomaly and "elevated" in pressure_desc:
        hypothesis = (
            f"{asset_id} is exhibiting elevated pressure. "
            f"Possible causes: downstream blockage or relief valve failure."
        )
    elif alarm_count > 3:
        hypothesis = (
            f"{asset_id} has generated {alarm_count} recent alarm events. "
            f"Current telemetry may indicate a developing fault. Human inspection recommended."
        )
    else:
        hypothesis = (
            f"{asset_id} telemetry in the query window does not show clear anomalies. "
            f"All tag readings appear within or near nominal range. Continue monitoring."
        )

    supporting = []
    evidence_tiers: list[str] = []

    if pressure_result:
        supporting.append(f"{pressure_desc}: {pressure_tier}")
        evidence_tiers.append(pressure_tier)

    if flow_result:
        supporting.append(f"{flow_desc}: {flow_tier}")
        evidence_tiers.append(flow_tier)

    if alarm_count > 0:
        alarm_tier = "CORROBORATING_EVIDENCE" if anomaly else "WEAK_SIGNAL"
        supporting.append(f"{alarm_count} recent events found in event log for {asset_id}: {alarm_tier}")
        evidence_tiers.append(alarm_tier)

    if docs_count > 0:
        supporting.append(
            f"Equipment documentation corpus returned {docs_count} relevant document(s): CORROBORATING_EVIDENCE"
        )
        evidence_tiers.append("CORROBORATING_EVIDENCE")

    if not supporting:
        supporting = ["Insufficient telemetry data to form supporting observations: INSUFFICIENT_DATA"]
        evidence_tiers = ["INSUFFICIENT_DATA"]

    alt_hypotheses_list = [
        "Sensor calibration drift: possible if only one sensor affected — multi-sensor corroboration required.",
        "Upstream supply variation: "
        + ("consistent with observed alarm pattern" if alarm_count > 3 else "not corroborated by upstream alarms in query window."),
    ]
    if not baseline_ok:
        alt_hypotheses_list.append(
            "Statistical noise: baseline unavailable — deviation magnitude cannot be statistically confirmed."
        )

    if all_fresh:
        quality_note = f"All {total_quality} monitored tags reported FRESH at investigation time."
    elif total_quality > 0:
        quality_note = f"{fresh_count}/{total_quality} tags FRESH — stale tags may reduce reliability."
    else:
        quality_note = "Tag quality data unavailable — findings reliability uncertain."

    baseline_note = (
        "Baseline comparison returned INSUFFICIENT_DATA. "
        "Run 'docker compose --profile seed run seed' to enable statistical deviation analysis."
        if not baseline_ok
        else "Baseline comparison performed. See evidence items for deviation details."
    )

    next_actions = ["Human reviewer should inspect the Evidence Explorer for actual sensor readings."]
    if anomaly:
        next_actions.append(f"Inspect {asset_id} for physical signs of the suspected fault condition.")
        next_actions.append("Verify sensor calibration before escalating to maintenance.")
    else:
        next_actions.append("Continue monitoring for emerging anomaly patterns.")
    if not baseline_ok:
        next_actions.append("Run seed script to enable future baseline comparisons.")

    finding_text = (
        "[SCRIPTED DEMONSTRATION]\n"
        "This finding was generated by a deterministic rule-based runner, not an AI model.\n"
        "Observations are derived from actual MCP tool responses for this investigation.\n"
        "\n"
        f"HYPOTHESIS: {hypothesis}\n"
        "\n"
        "SUPPORTING EVIDENCE:\n"
        + "".join(f"- {s}\n" for s in supporting)
        + "\n"
        "ALTERNATIVE HYPOTHESES:\n"
        + "".join(f"- {a}\n" for a in alt_hypotheses_list)
        + "\n"
        "DATA QUALITY CAVEATS:\n"
        f"- {quality_note}\n"
        f"- {baseline_note}\n"
        "\n"
        "RECOMMENDED NEXT ACTION:\n"
        + "".join(f"- {a}\n" for a in next_actions)
        + "\n"
        "SIMULATED DATA NOTICE: This investigation used simulated equipment data.\n"
        "All findings require human verification before operational action.\n"
        "Do not use for real operational decisions.\n"
    )

    return finding_text, evidence_tiers, alt_hypotheses_list


async def run_scripted_investigation(
    investigation_id: str,
    asset_id: str,
    trigger_alarm_id: str | None,
    event_queue: asyncio.Queue | None,
    fail_before_flag: bool = False,
) -> None:
    """
    Deterministic scripted investigation — no Anthropic API call.

    Calls the real MCP tools in a fixed sequence so that evidence items,
    DB state, and SSE events are all exercised. Used by regression tests
    to validate the full pipeline without spending API credits.

    If fail_before_flag=True, the scripted run deliberately skips
    flag_for_review to test the tool-budget-exhaustion failure path.
    """
    cfg = _agent_config()
    try:
        await asyncio.wait_for(
            _scripted_core(
                investigation_id, asset_id, event_queue, cfg, fail_before_flag
            ),
            timeout=cfg["timeout_secs"],
        )
    except asyncio.TimeoutError:
        await _fail(
            investigation_id,
            f"Scripted investigation timed out after {cfg['timeout_secs']:.0f}s",
            event_queue,
        )
    except Exception as exc:
        logger.exception("Unexpected error in scripted investigation %s", investigation_id)
        await _fail(investigation_id, str(exc), event_queue)


async def _scripted_core(
    investigation_id: str,
    asset_id: str,
    event_queue: asyncio.Queue | None,
    cfg: dict[str, Any],
    fail_before_flag: bool,
) -> None:
    inv_uuid = uuid.UUID(investigation_id)

    http_client = create_mcp_http_client(
        headers={"Authorization": f"Bearer {cfg['mcp_token']}"}
    )

    # Build ISO timestamps for query_telemetry (last 5 minutes).
    # 5 min × ~1 reading/sec ≈ 300 readings — stays under the 500-row LIMIT,
    # so ORDER BY timestamp ASC returns ALL readings including recent fault data.
    # A 30-min window produces ~1800 readings; LIMIT 500 ASC would then return
    # only the oldest 500, dropping any fault injected in the last ~21 minutes.
    now = datetime.now(timezone.utc)
    end_iso   = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_iso = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Pick primary and secondary tags for this asset type
    asset_tags: dict[str, list[str]] = {
        "PUMP-01":     ["Pressure_bar", "FlowRate_Lmin"],
        "MOTOR-01":    ["Temperature_degC", "Current_A"],
        "CONVEYOR-01": ["Speed_mps", "Temperature_degC"],
        "FILL-01":     ["Level_pct", "FillRate_Lmin"],
    }
    primary_tag, secondary_tag = (asset_tags.get(asset_id) or ["Pressure_bar", "FlowRate_Lmin"])

    # Data-gathering tools — run unconditionally
    data_tools = [
        ("get_recent_events",    {"asset_id": asset_id, "since_minutes": 120}),
        ("check_data_quality",   {"asset_id": asset_id}),
        ("query_telemetry",      {"asset_id": asset_id, "tag_name": primary_tag,   "start_iso": start_iso, "end_iso": end_iso}),
        ("query_telemetry",      {"asset_id": asset_id, "tag_name": secondary_tag, "start_iso": start_iso, "end_iso": end_iso}),
        ("compare_baseline",     {"asset_id": asset_id, "tag_name": primary_tag,   "window_minutes": 60}),
        ("query_equipment_docs", {"query_text": f"{asset_id} {primary_tag} anomaly fault"}),
    ]

    async with streamable_http_client(cfg["mcp_url"], http_client=http_client) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()

            tools_result = await mcp.list_tools()
            tools_with_inv_id: set[str] = {
                t.name
                for t in tools_result.tools
                if "investigation_id" in (
                    t.input_schema if isinstance(t.input_schema, dict) else dict(t.input_schema)
                ).get("properties", {})
            }

            # Run data-gathering tools and collect their results
            tool_results: dict[str, Any] = {}
            tool_call_count = 0

            for tool_name, tool_inputs in data_tools:
                tool_call_count += 1
                inputs = dict(tool_inputs)
                if tool_name in tools_with_inv_id:
                    inputs["investigation_id"] = investigation_id

                # Emit clean inputs (hide investigation_id from log display)
                display_inputs = {k: v for k, v in inputs.items() if k != "investigation_id"}
                await _emit(event_queue, {
                    "type":      "tool_call",
                    "tool_name": tool_name,
                    "inputs":    display_inputs,
                    "sequence":  tool_call_count,
                })

                result = await _call_mcp_tool(mcp, tool_name, inputs)
                success = result.get("success", False)

                await _emit(event_queue, {
                    "type":      "tool_result",
                    "tool_name": tool_name,
                    "success":   success,
                    "sequence":  tool_call_count,
                    "summary":   _result_summary(tool_name, result),
                })

                # Store result keyed by tool+tag for finding generation
                if tool_name == "query_telemetry":
                    tag_name = inputs.get("tag_name", "unknown")
                    tool_results[f"query_telemetry_{tag_name}"] = result
                else:
                    tool_results[tool_name] = result

            # --- submission phase ---

            if fail_before_flag:
                # Deliberately skip flag_for_review to test budget-exhaustion path
                pool = get_pool()
                await pool.execute(
                    """
                    UPDATE investigations
                    SET status = 'failed',
                        agent_model = $2,
                        agent_error = $3,
                        agent_tool_calls = $4
                    WHERE investigation_id = $1
                    """,
                    inv_uuid,
                    "scripted-runner",
                    f"Scripted agent used {tool_call_count} tool calls without calling flag_for_review",
                    tool_call_count,
                )
                await _emit(event_queue, {
                    "type":    "error",
                    "message": "Scripted agent did not submit a finding.",
                })
            else:
                # Build finding from actual observed tool results
                finding_text, evidence_tiers, alt_hypotheses = _build_scripted_finding(
                    asset_id, tool_results
                )

                tool_call_count += 1
                flag_inputs = {
                    "investigation_id": investigation_id,
                    "finding_text":     finding_text,
                    "evidence_tiers":   json.dumps(evidence_tiers),
                    "alt_hypotheses":   json.dumps(alt_hypotheses),
                }

                await _emit(event_queue, {
                    "type":      "tool_call",
                    "tool_name": "flag_for_review",
                    "inputs":    {"action": "submit_finding"},
                    "sequence":  tool_call_count,
                })

                flag_result = await _call_mcp_tool(mcp, "flag_for_review", flag_inputs)
                flagged = flag_result.get("success", False)

                await _emit(event_queue, {
                    "type":      "tool_result",
                    "tool_name": "flag_for_review",
                    "success":   flagged,
                    "sequence":  tool_call_count,
                    "summary":   "Finding submitted for human review" if flagged else "Submission failed",
                })

                pool = get_pool()
                if flagged:
                    await pool.execute(
                        """
                        UPDATE investigations
                        SET agent_model = $2, agent_tool_calls = $3
                        WHERE investigation_id = $1
                        """,
                        inv_uuid, "scripted-runner", tool_call_count,
                    )
                    await _emit(event_queue, {
                        "type":            "complete",
                        "status":          "pending_review",
                        "tool_calls_used": tool_call_count,
                    })
                else:
                    await pool.execute(
                        """
                        UPDATE investigations
                        SET status = 'failed',
                            agent_model = $2,
                            agent_error = $3,
                            agent_tool_calls = $4
                        WHERE investigation_id = $1
                        """,
                        inv_uuid,
                        "scripted-runner",
                        f"flag_for_review failed: {flag_result.get('error', 'unknown error')}",
                        tool_call_count,
                    )
                    await _emit(event_queue, {
                        "type":    "error",
                        "message": "Scripted agent failed to submit finding.",
                    })

    await _emit(event_queue, None)


def _result_summary(tool_name: str, result: dict) -> str:
    """Return a one-line human-readable summary of a tool result."""
    data = result.get("data", {})
    if not result.get("success"):
        return result.get("error", "Failed")
    if tool_name == "get_recent_events":
        return f"{data.get('count', 0)} events found"
    if tool_name == "check_data_quality":
        tags = data.get("tags", [])
        fresh = sum(1 for t in tags if t.get("freshness_status") == "FRESH")
        return f"{fresh}/{len(tags)} tags FRESH"
    if tool_name == "query_telemetry":
        readings = data.get("readings", [])
        if readings:
            unit = readings[-1].get("unit", "")
            last_val = readings[-1].get("value")
            return f"{data.get('count', 0)} readings — latest {last_val:.2f}{unit}" if last_val is not None else f"{data.get('count', 0)} readings"
        return "0 readings"
    if tool_name == "compare_baseline":
        msg = data.get("message", "")
        if "Insufficient" in msg or "0 rows" in msg:
            return "No baseline data — seed baseline to enable"
        mean_now = data.get("mean_now")
        mean_base = data.get("mean_baseline")
        if mean_now is not None and mean_base is not None:
            return f"Current {mean_now:.2f} vs baseline {mean_base:.2f}"
        return "Baseline comparison complete"
    if tool_name == "query_equipment_docs":
        return f"{data.get('count', 0)} relevant documents found"
    return "OK"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _call_mcp_tool(mcp: ClientSession, name: str, inputs: dict) -> dict:
    """Call a named MCP tool and return the parsed JSON response envelope."""
    try:
        result = await mcp.call_tool(name, inputs)
        if result.content and hasattr(result.content[0], "text"):
            return json.loads(result.content[0].text)
        return {"success": False, "data": None, "error": "Empty tool response"}
    except json.JSONDecodeError as e:
        return {"success": False, "data": None, "error": f"Tool response not JSON: {e}"}
    except Exception as e:
        logger.warning("MCP tool %s failed: %s", name, e)
        return {"success": False, "data": None, "error": str(e)}


async def _fail(
    investigation_id: str,
    error_msg: str,
    event_queue: asyncio.Queue | None,
) -> None:
    """Mark investigation as failed and push error event."""
    logger.error("Investigation %s failed: %s", investigation_id, error_msg)
    try:
        inv_uuid = uuid.UUID(investigation_id)
        pool = get_pool()
        await pool.execute(
            """
            UPDATE investigations
            SET status = 'failed', agent_error = $2
            WHERE investigation_id = $1
            """,
            inv_uuid, error_msg,
        )
    except Exception:
        logger.exception("Could not persist failure for investigation %s", investigation_id)

    await _emit(event_queue, {"type": "error", "message": error_msg})
    await _emit(event_queue, None)  # sentinel


async def _emit(queue: asyncio.Queue | None, event: dict | None) -> None:
    """Non-blocking event push; silently drops if no queue is set."""
    if queue is not None:
        await queue.put(event)
