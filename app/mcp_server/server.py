"""
FactoryIQ MCP Server — Milestone 2.

Seven read-only investigation tools exposed via MCP streamable-HTTP transport.
Bearer token auth is enforced by BearerAuthASGI (wraps the mounted sub-app)
before any tool reaches this server.

Tool contracts:
  - All tools validate inputs and return a {"success", "data", "error"} envelope.
  - No tool writes telemetry, approves findings, or controls equipment.
  - flag_for_review transitions investigation to pending_review; it does NOT approve.
  - Ground-truth (fault type labels, scenario IDs) is never stored here.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer

from db import get_pool
from mcp_server.corpus import search_docs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MCP_TOKEN: str = os.environ.get("MCP_BEARER_TOKEN", "changeme")

ALLOWED_ASSETS: set[str] = {"CONVEYOR-01", "PUMP-01", "MOTOR-01", "FILL-01"}
ASSET_TAGS: dict[str, list[str]] = {
    "CONVEYOR-01": ["Speed_mps", "Temperature_degC"],
    "PUMP-01": ["Temperature_degC", "Pressure_bar", "Vibration_mm_s", "FlowRate_Lmin"],
    "MOTOR-01": ["Current_A", "Temperature_degC", "Speed_rpm"],
    "FILL-01": ["Level_pct", "FillRate_Lmin", "Temperature_degC"],
}

EVIDENCE_TIERS = frozenset({
    "CONFIRMED_OBSERVATION", "STATISTICAL_SIGNAL",
    "CORROBORATING_EVIDENCE", "WEAK_SIGNAL", "INSUFFICIENT_DATA",
})

# ---------------------------------------------------------------------------
# MCPServer instance
# ---------------------------------------------------------------------------
mcp = MCPServer(
    name="FactoryIQ",
    description=(
        "Industrial AI Reliability Testbed — read-only investigation tools. "
        "All tools operate on live telemetry, alarms, and equipment documentation. "
        "No tool writes to equipment or approves findings."
    ),
    version="0.2.0",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: dict) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg}


def _validate_asset(asset_id: str) -> str | None:
    if asset_id not in ALLOWED_ASSETS:
        return f"Unknown asset_id '{asset_id}'. Valid: {sorted(ALLOWED_ASSETS)}"
    return None


def _validate_tag(asset_id: str, tag_name: str) -> str | None:
    tags = ASSET_TAGS.get(asset_id, [])
    if tag_name not in tags:
        return f"Unknown tag_name '{tag_name}' for asset '{asset_id}'. Valid: {tags}"
    return None


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _quality_tier(rows: list[dict]) -> str:
    if not rows:
        return "INSUFFICIENT_DATA"
    good = sum(1 for r in rows if r.get("opc_quality_label") == "Good")
    if good / len(rows) >= 0.9:
        return "CONFIRMED_OBSERVATION"
    if good / len(rows) >= 0.5:
        return "WEAK_SIGNAL"
    return "INSUFFICIENT_DATA"


async def _log_evidence(
    investigation_id: str,
    tool_name: str,
    tool_inputs: dict,
    tool_output: dict,
    evidence_tier: str,
    citation_text: str | None = None,
) -> None:
    if evidence_tier not in EVIDENCE_TIERS:
        evidence_tier = "WEAK_SIGNAL"
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        logger.warning("Invalid investigation_id UUID: %s", investigation_id)
        return
    try:
        pool = get_pool()
        seq = await pool.fetchval(
            "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM evidence_items WHERE investigation_id = $1",
            inv_uuid,
        )
        await pool.execute(
            """
            INSERT INTO evidence_items
              (investigation_id, sequence_num, tool_name, tool_inputs,
               tool_output, evidence_tier, citation_text)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            inv_uuid,
            seq,
            tool_name,
            tool_inputs,
            tool_output,
            evidence_tier,
            citation_text,
        )
    except Exception:
        logger.exception("Evidence logging failed for investigation %s", investigation_id)


# ---------------------------------------------------------------------------
# ASGI auth middleware — wraps the streamable_http_app
# ---------------------------------------------------------------------------

class BearerAuthASGI:
    """Pure ASGI middleware: validates Authorization: Bearer <token> for HTTP
    requests. Lifespan events pass through without auth.
    Does not buffer streaming responses."""

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            await self._app(scope, receive, send)
            return

        if scope["type"] == "http":
            headers = {k: v for k, v in scope.get("headers", [])}
            raw_auth = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
            token = raw_auth[7:] if raw_auth.startswith("Bearer ") else ""
            if token != self._token:
                body = b"Unauthorized"
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"text/plain"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return

        await self._app(scope, receive, send)


def build_mcp_asgi(token: str) -> Any:
    """Return the BearerAuthASGI-wrapped MCP streamable HTTP app."""
    starlette_app = mcp.streamable_http_app(streamable_http_path="/")
    return BearerAuthASGI(starlette_app, token)


# ---------------------------------------------------------------------------
# Tool 1: query_telemetry
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Retrieve time-series measurements for a specific asset tag within a bounded "
    "time window. Returns raw readings with OPC UA quality codes. "
    "Maximum window: 24 hours. Maximum rows: 1000."
))
async def query_telemetry(
    asset_id: str,
    tag_name: str,
    start_iso: str,
    end_iso: str,
    limit: int = 500,
    investigation_id: str = "",
) -> dict:
    err = _validate_asset(asset_id)
    if err:
        return _err(err)
    err = _validate_tag(asset_id, tag_name)
    if err:
        return _err(err)

    start = _parse_iso(start_iso)
    end = _parse_iso(end_iso)
    if start is None:
        return _err(f"Invalid start_iso: '{start_iso}'. Use ISO 8601, e.g. 2026-11-21T10:00:00Z")
    if end is None:
        return _err(f"Invalid end_iso: '{end_iso}'. Use ISO 8601, e.g. 2026-11-21T11:00:00Z")
    if start >= end:
        return _err("start_iso must be before end_iso")
    if (end - start).total_seconds() > 86400:
        return _err("Time window exceeds 24-hour maximum")

    limit = max(1, min(limit, 1000))

    try:
        pool = get_pool()
        rows = await pool.fetch(
            """
            SELECT timestamp, value, opc_quality_code, opc_quality_label, unit, source
            FROM telemetry
            WHERE asset_id = $1 AND tag_name = $2
              AND timestamp >= $3 AND timestamp <= $4
            ORDER BY timestamp ASC
            LIMIT $5
            """,
            asset_id, tag_name, start, end, limit,
        )
    except Exception:
        logger.exception("DB error in query_telemetry")
        return _err("Database query failed")

    readings = [
        {
            "timestamp": r["timestamp"].isoformat(),
            "value": r["value"],
            "opc_quality_code": r["opc_quality_code"],
            "opc_quality_label": r["opc_quality_label"],
            "unit": r["unit"],
            "source": r["source"],
            "is_simulated": True,
        }
        for r in rows
    ]

    result = _ok({
        "asset_id": asset_id,
        "tag_name": tag_name,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "count": len(readings),
        "readings": readings,
        "is_simulated": True,
    })

    if investigation_id:
        tier = _quality_tier(readings)
        await _log_evidence(
            investigation_id, "query_telemetry",
            {"asset_id": asset_id, "tag_name": tag_name,
             "start_iso": start_iso, "end_iso": end_iso},
            result, tier,
            f"{len(readings)} readings for {asset_id}/{tag_name}",
        )

    return result


# ---------------------------------------------------------------------------
# Tool 2: query_alarms
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Retrieve equipment alarms with timestamps, severity, and observable conditions. "
    "Alarms describe symptoms only — they do not identify root causes. "
    "Maximum: 100 alarms. Default lookback: 24 hours."
))
async def query_alarms(
    asset_id: str = "",
    severity: str = "",
    since_iso: str = "",
    limit: int = 20,
    investigation_id: str = "",
) -> dict:
    limit = max(1, min(limit, 100))
    valid_severities = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    if asset_id and asset_id not in ALLOWED_ASSETS:
        return _err(f"Unknown asset_id '{asset_id}'. Valid: {sorted(ALLOWED_ASSETS)}")
    if severity and severity.upper() not in valid_severities:
        return _err(f"Invalid severity '{severity}'. Valid: {sorted(valid_severities)}")

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    if since_iso:
        parsed = _parse_iso(since_iso)
        if parsed is None:
            return _err(f"Invalid since_iso: '{since_iso}'")
        since = parsed

    try:
        pool = get_pool()
        conditions = ["triggered_at >= $1"]
        params: list = [since]

        if asset_id:
            params.append(asset_id)
            conditions.append(f"asset_id = ${len(params)}")
        if severity:
            params.append(severity.upper())
            conditions.append(f"severity = ${len(params)}")

        params.append(limit)
        where = " AND ".join(conditions)
        rows = await pool.fetch(
            f"""
            SELECT alarm_id, asset_id, alarm_type, severity, message,
                   triggered_at, acknowledged_at, raw_value, threshold, is_simulated
            FROM alarms WHERE {where}
            ORDER BY triggered_at DESC LIMIT ${len(params)}
            """,
            *params,
        )
    except Exception:
        logger.exception("DB error in query_alarms")
        return _err("Database query failed")

    alarms = [
        {
            "alarm_id": str(r["alarm_id"]),
            "asset_id": r["asset_id"],
            "alarm_type": r["alarm_type"],
            "severity": r["severity"],
            "message": r["message"],
            "triggered_at": r["triggered_at"].isoformat(),
            "acknowledged_at": r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None,
            "raw_value": r["raw_value"],
            "threshold": r["threshold"],
            "is_simulated": r["is_simulated"],
        }
        for r in rows
    ]

    result = _ok({
        "count": len(alarms),
        "alarms": alarms,
        "filters": {"asset_id": asset_id or None, "severity": severity or None,
                    "since_iso": since.isoformat()},
    })

    if investigation_id and alarms:
        await _log_evidence(
            investigation_id, "query_alarms",
            {"asset_id": asset_id, "severity": severity, "since_iso": since_iso},
            result, "CORROBORATING_EVIDENCE",
            f"Retrieved {len(alarms)} alarms",
        )

    return result


# ---------------------------------------------------------------------------
# Tool 3: query_equipment_docs
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Retrieve relevant equipment documentation using keyword matching. "
    "Returns up to top_k documents with source references. "
    "Documents are illustrative; labeled as such in source_ref. "
    "Returns empty list when no relevant documents match the query."
))
async def query_equipment_docs(
    query_text: str,
    asset_type: str = "",
    top_k: int = 3,
    investigation_id: str = "",
) -> dict:
    if not query_text or not query_text.strip():
        return _err("query_text must not be empty")
    if len(query_text) > 500:
        return _err("query_text exceeds 500-character limit")
    top_k = max(1, min(top_k, 5))

    docs = search_docs(query_text, asset_type=asset_type or None, top_k=top_k)

    result = _ok({
        "query_text": query_text,
        "asset_type_filter": asset_type or None,
        "count": len(docs),
        "documents": [
            {
                "title": d["title"],
                "asset_type": d["asset_type"],
                "doc_type": d["doc_type"],
                "content": d["content"],
                "source_ref": d["source_ref"],
                "is_illustrative": True,
            }
            for d in docs
        ],
        "retrieval_method": "keyword_match",
        "note": "Illustrative corpus only. Milestone 6 adds pgvector semantic retrieval.",
    })

    if investigation_id and docs:
        await _log_evidence(
            investigation_id, "query_equipment_docs",
            {"query_text": query_text, "asset_type": asset_type},
            result, "CORROBORATING_EVIDENCE",
            "; ".join(d["source_ref"] for d in docs),
        )

    return result


# ---------------------------------------------------------------------------
# Tool 4: compare_baseline
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Compare current measurements against the 7-day seeded baseline for an asset tag. "
    "Returns mean, stddev, z-score, and evidence tier. "
    "Returns INSUFFICIENT_DATA when fewer than 100 baseline rows exist. "
    "Baseline excludes the most recent 5 minutes to avoid fault contamination."
))
async def compare_baseline(
    asset_id: str,
    tag_name: str,
    window_minutes: int = 60,
    investigation_id: str = "",
) -> dict:
    err = _validate_asset(asset_id)
    if err:
        return _err(err)
    err = _validate_tag(asset_id, tag_name)
    if err:
        return _err(err)
    window_minutes = max(1, min(window_minutes, 1440))

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(minutes=window_minutes)
    baseline_end = now - timedelta(minutes=5)   # exclude last 5 min from baseline
    baseline_start = baseline_end - timedelta(days=7)

    try:
        pool = get_pool()

        # Baseline statistics from SEED_BASELINE rows with Good quality
        baseline_stats = await pool.fetchrow(
            """
            SELECT
                COUNT(*) AS cnt,
                AVG(value) AS mean,
                STDDEV(value) AS stddev
            FROM telemetry
            WHERE asset_id = $1 AND tag_name = $2
              AND source = 'SEED_BASELINE'
              AND opc_quality_label = 'Good'
              AND timestamp >= $3 AND timestamp < $4
            """,
            asset_id, tag_name, baseline_start, baseline_end,
        )

        baseline_count = baseline_stats["cnt"] or 0
        if baseline_count < 100:
            result = _ok({
                "asset_id": asset_id,
                "tag_name": tag_name,
                "baseline_available": False,
                "baseline_row_count": baseline_count,
                "evidence_tier": "INSUFFICIENT_DATA",
                "message": (
                    f"Insufficient baseline data ({baseline_count} rows). "
                    "Run 'docker compose --profile seed run seed' to populate 7-day baseline."
                ),
            })
            if investigation_id:
                await _log_evidence(
                    investigation_id, "compare_baseline",
                    {"asset_id": asset_id, "tag_name": tag_name, "window_minutes": window_minutes},
                    result, "INSUFFICIENT_DATA",
                )
            return result

        baseline_mean: float = float(baseline_stats["mean"])
        baseline_stddev: float = float(baseline_stats["stddev"] or 0.001)

        # Current window stats (all quality codes — quality is reported separately)
        current_stats = await pool.fetchrow(
            """
            SELECT COUNT(*) AS cnt, AVG(value) AS mean,
                   MIN(value) AS min_val, MAX(value) AS max_val
            FROM telemetry
            WHERE asset_id = $1 AND tag_name = $2
              AND timestamp >= $3 AND timestamp <= $4
              AND opc_quality_label = 'Good'
            """,
            asset_id, tag_name, current_start, now,
        )

        current_count = current_stats["cnt"] or 0
        if current_count == 0:
            result = _ok({
                "asset_id": asset_id,
                "tag_name": tag_name,
                "baseline_available": True,
                "baseline_mean": baseline_mean,
                "baseline_stddev": baseline_stddev,
                "baseline_row_count": baseline_count,
                "current_available": False,
                "evidence_tier": "INSUFFICIENT_DATA",
                "message": "No Good-quality readings in current window.",
            })
            if investigation_id:
                await _log_evidence(
                    investigation_id, "compare_baseline",
                    {"asset_id": asset_id, "tag_name": tag_name, "window_minutes": window_minutes},
                    result, "INSUFFICIENT_DATA",
                )
            return result

        current_mean = float(current_stats["mean"])
        z_score = (current_mean - baseline_mean) / baseline_stddev
        abs_z = abs(z_score)

        if abs_z >= 2.0:
            tier = "STATISTICAL_SIGNAL"
        elif abs_z >= 1.0:
            tier = "WEAK_SIGNAL"
        else:
            tier = "CONFIRMED_OBSERVATION"

        result = _ok({
            "asset_id": asset_id,
            "tag_name": tag_name,
            "baseline_available": True,
            "baseline_mean": round(baseline_mean, 4),
            "baseline_stddev": round(baseline_stddev, 4),
            "baseline_row_count": baseline_count,
            "current_mean": round(current_mean, 4),
            "current_row_count": current_count,
            "delta": round(current_mean - baseline_mean, 4),
            "z_score": round(z_score, 3),
            "evidence_tier": tier,
            "window_minutes": window_minutes,
            "is_simulated": True,
        })

    except Exception:
        logger.exception("DB error in compare_baseline")
        return _err("Database query failed")

    if investigation_id:
        await _log_evidence(
            investigation_id, "compare_baseline",
            {"asset_id": asset_id, "tag_name": tag_name, "window_minutes": window_minutes},
            result, tier,
            f"{asset_id}/{tag_name} z-score={z_score:.2f} vs {baseline_count} baseline rows",
        )

    return result


# ---------------------------------------------------------------------------
# Tool 5: check_data_quality
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Check data quality for an asset: OPC UA device-reported quality codes AND "
    "ingestion-inferred freshness status. "
    "A tag can have opc_quality_label=Good but freshness_status=STALE — "
    "that last good reading must NOT be used as current evidence. "
    "Provide tag_names as comma-separated string, or leave empty for all asset tags."
))
async def check_data_quality(
    asset_id: str,
    tag_names: str = "",
    since_minutes: int = 60,
    investigation_id: str = "",
) -> dict:
    err = _validate_asset(asset_id)
    if err:
        return _err(err)
    since_minutes = max(1, min(since_minutes, 1440))

    requested_tags: list[str] = []
    if tag_names:
        for t in tag_names.split(","):
            t = t.strip()
            if t:
                v = _validate_tag(asset_id, t)
                if v:
                    return _err(v)
                requested_tags.append(t)
    if not requested_tags:
        requested_tags = ASSET_TAGS.get(asset_id, [])

    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

    try:
        pool = get_pool()

        # Freshness status from tag_health
        health_rows = await pool.fetch(
            """
            SELECT tag_name, last_update, freshness_status, staleness_threshold_seconds
            FROM tag_health
            WHERE asset_id = $1 AND tag_name = ANY($2)
            """,
            asset_id, requested_tags,
        )
        health_map = {r["tag_name"]: r for r in health_rows}

        # Quality distribution over the recent window
        quality_rows = await pool.fetch(
            """
            SELECT tag_name,
                   COUNT(*) FILTER (WHERE opc_quality_label = 'Good') AS good_count,
                   COUNT(*) FILTER (WHERE opc_quality_label = 'Bad') AS bad_count,
                   COUNT(*) FILTER (WHERE opc_quality_label = 'Uncertain') AS uncertain_count,
                   COUNT(*) AS total_count,
                   MAX(timestamp) AS latest_ts
            FROM telemetry
            WHERE asset_id = $1 AND tag_name = ANY($2) AND timestamp >= $3
            GROUP BY tag_name
            """,
            asset_id, requested_tags, since,
        )
        quality_map = {r["tag_name"]: r for r in quality_rows}

    except Exception:
        logger.exception("DB error in check_data_quality")
        return _err("Database query failed")

    tag_summaries = []
    overall_issues: list[str] = []

    for tag in requested_tags:
        h = health_map.get(tag)
        q = quality_map.get(tag)

        freshness = h["freshness_status"] if h else "MISSING"
        last_update = h["last_update"].isoformat() if (h and h["last_update"]) else None
        staleness_threshold = h["staleness_threshold_seconds"] if h else None

        good_count = q["good_count"] if q else 0
        bad_count = q["bad_count"] if q else 0
        uncertain_count = q["uncertain_count"] if q else 0
        total_count = q["total_count"] if q else 0
        latest_ts = q["latest_ts"].isoformat() if (q and q["latest_ts"]) else None

        issues = []
        if freshness == "STALE":
            issues.append("STALE: tag stopped publishing; last stored reading cannot be treated as current")
        if freshness == "MISSING":
            issues.append("MISSING: no readings received since startup")
        if total_count > 0 and bad_count > 0:
            pct = round(bad_count / total_count * 100, 1)
            issues.append(f"BAD_QUALITY: {pct}% of recent readings have Bad OPC UA quality code")
        if total_count > 0 and uncertain_count / total_count > 0.5:
            issues.append("UNCERTAIN_QUALITY: >50% of recent readings are Uncertain quality")
        if total_count == 0:
            issues.append("NO_RECENT_DATA: no readings in the requested window")

        if issues:
            overall_issues.extend(f"{tag}: {i}" for i in issues)

        tag_summaries.append({
            "tag_name": tag,
            "freshness_status": freshness,
            "last_update": last_update,
            "staleness_threshold_seconds": staleness_threshold,
            "recent_good_count": good_count,
            "recent_bad_count": bad_count,
            "recent_uncertain_count": uncertain_count,
            "recent_total_count": total_count,
            "latest_reading_ts": latest_ts,
            "issues": issues,
            "usable_as_evidence": (
                freshness == "FRESH"
                and total_count > 0
                and (bad_count / max(total_count, 1)) < 0.1
            ),
        })

    tier = "CONFIRMED_OBSERVATION" if not overall_issues else "INSUFFICIENT_DATA"

    result = _ok({
        "asset_id": asset_id,
        "since_minutes": since_minutes,
        "tags": tag_summaries,
        "overall_issues": overall_issues,
        "evidence_tier": tier,
        "quality_note": (
            "freshness_status is independent of opc_quality_label. "
            "A tag with opc_quality_label=Good but freshness_status=STALE "
            "must NOT be used as current evidence."
        ),
    })

    if investigation_id:
        await _log_evidence(
            investigation_id, "check_data_quality",
            {"asset_id": asset_id, "tag_names": tag_names, "since_minutes": since_minutes},
            result, tier,
            f"{len(overall_issues)} quality issues for {asset_id}",
        )

    return result


# ---------------------------------------------------------------------------
# Tool 6: get_recent_events
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Retrieve observable alarm and equipment events in chronological order. "
    "Events describe symptoms, not root causes. "
    "event_types: comma-separated list of 'alarms' (more types in future milestones). "
    "Default: all event types, last 60 minutes."
))
async def get_recent_events(
    asset_id: str = "",
    event_types: str = "alarms",
    limit: int = 20,
    since_minutes: int = 60,
    investigation_id: str = "",
) -> dict:
    limit = max(1, min(limit, 100))
    since_minutes = max(1, min(since_minutes, 1440))

    if asset_id and asset_id not in ALLOWED_ASSETS:
        return _err(f"Unknown asset_id '{asset_id}'. Valid: {sorted(ALLOWED_ASSETS)}")

    requested_types = {t.strip().lower() for t in event_types.split(",") if t.strip()}
    valid_types = {"alarms"}
    unknown = requested_types - valid_types
    if unknown:
        return _err(f"Unknown event_types: {unknown}. Valid: {valid_types}")

    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    events: list[dict] = []

    try:
        pool = get_pool()

        if "alarms" in requested_types:
            if asset_id:
                rows = await pool.fetch(
                    """
                    SELECT alarm_id, asset_id, alarm_type, severity, message,
                           triggered_at, acknowledged_at, raw_value, threshold
                    FROM alarms
                    WHERE asset_id = $1 AND triggered_at >= $2
                    ORDER BY triggered_at DESC LIMIT $3
                    """,
                    asset_id, since, limit,
                )
            else:
                rows = await pool.fetch(
                    """
                    SELECT alarm_id, asset_id, alarm_type, severity, message,
                           triggered_at, acknowledged_at, raw_value, threshold
                    FROM alarms
                    WHERE triggered_at >= $1
                    ORDER BY triggered_at DESC LIMIT $2
                    """,
                    since, limit,
                )
            for r in rows:
                events.append({
                    "event_type": "alarm",
                    "event_id": str(r["alarm_id"]),
                    "asset_id": r["asset_id"],
                    "timestamp": r["triggered_at"].isoformat(),
                    "severity": r["severity"],
                    "description": r["message"],
                    "detail": {
                        "alarm_type": r["alarm_type"],
                        "raw_value": r["raw_value"],
                        "threshold": r["threshold"],
                        "acknowledged": r["acknowledged_at"] is not None,
                    },
                })

    except Exception:
        logger.exception("DB error in get_recent_events")
        return _err("Database query failed")

    events.sort(key=lambda e: e["timestamp"])

    result = _ok({
        "count": len(events),
        "events": events,
        "since_iso": since.isoformat(),
        "filters": {"asset_id": asset_id or None, "event_types": list(requested_types)},
    })

    if investigation_id and events:
        await _log_evidence(
            investigation_id, "get_recent_events",
            {"asset_id": asset_id, "event_types": event_types, "since_minutes": since_minutes},
            result, "CORROBORATING_EVIDENCE",
            f"{len(events)} events retrieved",
        )

    return result


# ---------------------------------------------------------------------------
# Tool 7: flag_for_review
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Record an investigation finding as PENDING HUMAN REVIEW. "
    "This tool does NOT approve the finding. Human approval requires a separate "
    "authenticated API call (POST /api/investigations/{id}/approve) with a "
    "human-issued session token. The agent cannot approve its own findings. "
    "evidence_tiers: JSON array of {tag, tier, rationale} objects. "
    "alt_hypotheses: JSON array of alternative hypothesis strings."
))
async def flag_for_review(
    investigation_id: str,
    finding_text: str,
    evidence_tiers: str,
    alt_hypotheses: str = "[]",
) -> dict:
    if not investigation_id or not investigation_id.strip():
        return _err("investigation_id is required")
    if not finding_text or not finding_text.strip():
        return _err("finding_text must not be empty")
    if len(finding_text) > 5000:
        return _err("finding_text exceeds 5000-character limit")

    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        return _err(f"Invalid investigation_id UUID: '{investigation_id}'")

    try:
        tiers_parsed = json.loads(evidence_tiers)
        if not isinstance(tiers_parsed, list):
            return _err("evidence_tiers must be a JSON array")
    except json.JSONDecodeError as e:
        return _err(f"evidence_tiers is not valid JSON: {e}")

    try:
        alts_parsed = json.loads(alt_hypotheses)
        if not isinstance(alts_parsed, list):
            return _err("alt_hypotheses must be a JSON array")
    except json.JSONDecodeError as e:
        return _err(f"alt_hypotheses is not valid JSON: {e}")

    try:
        pool = get_pool()

        inv = await pool.fetchrow(
            "SELECT investigation_id, status FROM investigations WHERE investigation_id = $1",
            inv_uuid,
        )
        if inv is None:
            return _err(f"Investigation '{investigation_id}' not found")
        if inv["status"] in ("approved", "rejected"):
            return _err(f"Investigation is already {inv['status']} — cannot flag again")

        await pool.execute(
            """
            UPDATE investigations
            SET status = 'pending_review',
                finding_text = $2,
                evidence_summary = $3,
                alt_hypotheses = $4,
                completed_at = now()
            WHERE investigation_id = $1
            """,
            inv_uuid,
            finding_text,
            tiers_parsed,
            alts_parsed,
        )

    except Exception:
        logger.exception("DB error in flag_for_review")
        return _err("Database update failed")

    return _ok({
        "investigation_id": investigation_id,
        "status": "pending_review",
        "finding_text": finding_text,
        "evidence_tiers": tiers_parsed,
        "alt_hypotheses": alts_parsed,
        "pending_human_approval": True,
        "approval_note": (
            "This finding requires human review. "
            "POST /api/investigations/{id}/approve with a human session token to approve."
        ),
    })
