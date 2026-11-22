"""
Milestone 3 regression tests using the scripted (no-LLM) runner.

These tests exercise the full investigation pipeline — MCP tool calls,
evidence logging, DB persistence, SSE streaming, and human approval —
without making any Anthropic API calls.

They require:
  - The Docker stack to be running (APP_URL, POSTGRES_PORT)
  - ALLOW_SCRIPTED_RUNNER=true in the app container (set via .env)

Run:
  APP_URL=http://localhost:8080 POSTGRES_PORT=5433 pytest test_milestone3_mock.py -v
"""

import asyncio
import json
import os
import re
import uuid

import asyncpg
import httpx
import pytest
import pytest_asyncio

APP_URL   = os.environ.get("APP_URL",   "http://localhost:8000")
MCP_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "changeme")
HUMAN_TOKEN = os.environ.get("MCP_HUMAN_TOKEN", "human-changeme")

POSTGRES_DSN = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'factoryiq')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'factoryiq')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'factoryiq')}"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _wait_for_status(http, inv_id: str, timeout_secs: float = 60.0) -> str:
    deadline = asyncio.get_event_loop().time() + timeout_secs
    while asyncio.get_event_loop().time() < deadline:
        r = await http.get(f"{APP_URL}/api/investigations/{inv_id}")
        assert r.status_code == 200
        status = r.json()["status"]
        if status != "in_progress":
            return status
        await asyncio.sleep(2)
    return "in_progress"


async def _check_scripted_runner_available(http) -> None:
    """Skip if ALLOW_SCRIPTED_RUNNER is not enabled in the app container.

    When the feature is disabled the endpoint returns 404 with detail='Not found'.
    When enabled but the investigation doesn't exist it returns 404 with
    detail='Investigation not found' — that means the feature IS available.
    """
    fake = str(uuid.uuid4())
    r = await http.post(f"{APP_URL}/api/investigations/{fake}/scripted-run")
    if r.status_code == 404 and r.json().get("detail", "").lower() == "not found":
        pytest.skip("ALLOW_SCRIPTED_RUNNER not enabled in app container")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def http():
    async with httpx.AsyncClient(timeout=30) as client:
        yield client


@pytest_asyncio.fixture
async def db():
    conn = await asyncpg.connect(POSTGRES_DSN)
    yield conn
    await conn.close()


@pytest_asyncio.fixture
async def scripted_inv(http):
    """
    Create a fresh investigation, run the scripted agent, wait for completion.
    Returns (investigation_id, final_status).
    Skips if scripted runner is not available.
    """
    await _check_scripted_runner_available(http)

    cr = await http.post(f"{APP_URL}/api/investigations", json={"asset_id": "PUMP-01"})
    assert cr.status_code == 200, cr.text
    inv_id = cr.json()["investigation_id"]

    rr = await http.post(f"{APP_URL}/api/investigations/{inv_id}/scripted-run")
    assert rr.status_code == 200, rr.text
    assert rr.json()["mode"] == "scripted"

    final_status = await _wait_for_status(http, inv_id, timeout_secs=60)
    assert final_status == "pending_review", (
        f"Scripted investigation ended with '{final_status}' instead of "
        f"'pending_review' — check scripted runner implementation."
    )
    return inv_id, final_status


@pytest_asyncio.fixture
async def failed_scripted_inv(http):
    """
    Run the scripted agent in fail_before_flag mode to test the
    tool-budget-exhaustion failure path.
    """
    await _check_scripted_runner_available(http)

    cr = await http.post(f"{APP_URL}/api/investigations", json={"asset_id": "PUMP-01"})
    assert cr.status_code == 200, cr.text
    inv_id = cr.json()["investigation_id"]

    rr = await http.post(
        f"{APP_URL}/api/investigations/{inv_id}/scripted-run",
        params={"fail_before_flag": "true"},
    )
    assert rr.status_code == 200, rr.text

    final_status = await _wait_for_status(http, inv_id, timeout_secs=60)
    assert final_status == "failed", (
        f"Expected 'failed' from fail_before_flag mode, got '{final_status}'"
    )
    return inv_id, final_status


# ---------------------------------------------------------------------------
# Scripted runner contract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scripted_run_endpoint_available(http):
    """ALLOW_SCRIPTED_RUNNER=true must expose the scripted-run endpoint."""
    await _check_scripted_runner_available(http)
    # If we reach here, the endpoint returned non-404 (likely 404 on nonexistent inv)
    # which means it IS enabled.


@pytest.mark.asyncio
async def test_scripted_run_requires_in_progress(http):
    """scripted-run on a completed investigation returns 409."""
    await _check_scripted_runner_available(http)

    cr = await http.post(f"{APP_URL}/api/investigations", json={"asset_id": "PUMP-01"})
    inv_id = cr.json()["investigation_id"]

    # First run → pending_review
    rr = await http.post(f"{APP_URL}/api/investigations/{inv_id}/scripted-run")
    assert rr.status_code == 200
    await _wait_for_status(http, inv_id, timeout_secs=60)

    # Second run → 409
    rr2 = await http.post(f"{APP_URL}/api/investigations/{inv_id}/scripted-run")
    assert rr2.status_code == 409, f"Expected 409, got {rr2.status_code}: {rr2.text}"


# ---------------------------------------------------------------------------
# AC3: Finding references asset/tag names
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_ac3_evidence_references_in_finding(scripted_inv, db):
    """
    AC3 (mocked): The scripted finding must reference the investigated asset
    and at least one known tag name, without using the paid Anthropic API.
    """
    inv_id, _ = scripted_inv
    inv = await db.fetchrow(
        "SELECT finding_text FROM investigations WHERE investigation_id=$1",
        uuid.UUID(inv_id),
    )
    finding = inv["finding_text"] or ""
    assert len(finding) > 50, "Scripted finding is too short"

    known_tokens = {
        "PUMP-01", "MOTOR-01", "CONVEYOR-01", "FILL-01",
        "Temperature_degC", "Vibration_mm_s", "Pressure_bar",
        "FlowRate_Lmin", "Current_A", "Speed_rpm", "Level_pct",
    }
    referenced = {t for t in known_tokens if t in finding}
    assert referenced, (
        f"Scripted finding does not reference any known asset or tag name. "
        f"Finding: {finding[:200]}"
    )


# ---------------------------------------------------------------------------
# AC4: No percentage confidence claims in finding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_ac4_no_confidence_percentages_in_finding(scripted_inv, db):
    """
    AC4 (mocked): Finding must not contain percentage confidence claims.
    """
    inv_id, _ = scripted_inv
    inv = await db.fetchrow(
        "SELECT finding_text FROM investigations WHERE investigation_id=$1",
        uuid.UUID(inv_id),
    )
    finding = (inv["finding_text"] or "").lower()
    pct_pattern = re.compile(r'\d+\s*%\s*(confident|confidence|probability|likelihood|certain)')
    match = pct_pattern.search(finding)
    assert match is None, (
        f"Scripted finding contains percentage confidence: '{match.group()}'"
    )


# ---------------------------------------------------------------------------
# AC7: Evidence items are recorded (scripted path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_ac7_evidence_items_recorded(scripted_inv, db):
    """
    AC7 (mocked): Scripted investigation must log evidence items for every
    tool call that accepts investigation_id.
    """
    inv_id, _ = scripted_inv
    rows = await db.fetch(
        """
        SELECT tool_name, sequence_num, evidence_tier, recorded_at
        FROM evidence_items
        WHERE investigation_id = $1
        ORDER BY sequence_num
        """,
        uuid.UUID(inv_id),
    )
    assert len(rows) >= 2, f"Expected ≥2 evidence items from scripted run, got {len(rows)}"

    valid_tiers = {
        "CONFIRMED_OBSERVATION", "STATISTICAL_SIGNAL", "CORROBORATING_EVIDENCE",
        "WEAK_SIGNAL", "INSUFFICIENT_DATA",
    }
    for row in rows:
        assert row["tool_name"] is not None
        assert row["evidence_tier"] in valid_tiers, f"Invalid tier: {row['evidence_tier']}"
        assert row["sequence_num"] > 0
        assert row["recorded_at"] is not None

    seqs = [r["sequence_num"] for r in rows]
    assert seqs == sorted(seqs), f"Evidence items not in order: {seqs}"


# ---------------------------------------------------------------------------
# AC9: Human approval after scripted run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_ac9_mcp_token_cannot_approve(scripted_inv, http):
    """
    AC9 (mocked): MCP bearer token must be rejected when attempting to approve
    a pending_review investigation.
    """
    inv_id, _ = scripted_inv
    r = await http.post(
        f"{APP_URL}/api/investigations/{inv_id}/approve",
        headers={"Authorization": f"Bearer {MCP_TOKEN}"},
        json={},
    )
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"


@pytest.mark.asyncio
async def test_mock_ac9_human_token_can_approve(scripted_inv, http):
    """
    AC9 (mocked): Human token must be able to approve a pending_review investigation.
    """
    inv_id, _ = scripted_inv
    r = await http.post(
        f"{APP_URL}/api/investigations/{inv_id}/approve",
        headers={"Authorization": f"Bearer {HUMAN_TOKEN}"},
        json={},
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# AC10: No scenario labels in finding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_ac10_no_scenario_labels(scripted_inv, db):
    """
    AC10 (mocked): Finding must not contain evaluation-framework labels.
    """
    inv_id, _ = scripted_inv
    inv = await db.fetchrow(
        "SELECT finding_text FROM investigations WHERE investigation_id=$1",
        uuid.UUID(inv_id),
    )
    finding = (inv["finding_text"] or "").lower()
    forbidden = {
        "bearing_wear_nominal", "scenario_id", "evaluation_scenario",
        "injected_sequence", "expected_conclusion",
    }
    for label in forbidden:
        assert label not in finding, (
            f"Scripted finding contains forbidden label '{label}'"
        )


# ---------------------------------------------------------------------------
# Agent metadata persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_agent_stores_model_name(scripted_inv, db):
    """Scripted runner must record agent_model and agent_tool_calls."""
    inv_id, _ = scripted_inv
    row = await db.fetchrow(
        "SELECT agent_model, agent_tool_calls FROM investigations WHERE investigation_id=$1",
        uuid.UUID(inv_id),
    )
    assert row["agent_model"] is not None, "agent_model column not set after scripted run"
    assert row["agent_tool_calls"] is not None and row["agent_tool_calls"] > 0, (
        "agent_tool_calls column not set or is zero"
    )


@pytest.mark.asyncio
async def test_mock_get_investigation_includes_agent_columns(scripted_inv, http):
    """GET /api/investigations/{id} must return agent_model and agent_tool_calls."""
    inv_id, _ = scripted_inv
    r = await http.get(f"{APP_URL}/api/investigations/{inv_id}")
    assert r.status_code == 200
    body = r.json()
    assert "agent_model" in body, "agent_model missing from GET response"
    assert "agent_tool_calls" in body, "agent_tool_calls missing from GET response"
    assert body["agent_model"] == "scripted-runner"
    assert body["agent_tool_calls"] > 0


# ---------------------------------------------------------------------------
# Failure mode: tool budget exhaustion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_budget_exhaustion_sets_failed_status(failed_scripted_inv, db):
    """
    When the agent uses all tool calls without calling flag_for_review,
    the investigation must reach 'failed' status (not 'in_progress' or hang).
    """
    inv_id, final_status = failed_scripted_inv
    assert final_status == "failed"

    row = await db.fetchrow(
        "SELECT status, agent_error, agent_tool_calls FROM investigations WHERE investigation_id=$1",
        uuid.UUID(inv_id),
    )
    assert row["status"] == "failed"
    assert row["agent_error"] is not None, "agent_error must be set on failure"
    assert "flag_for_review" in row["agent_error"], (
        f"Expected error to mention flag_for_review, got: {row['agent_error']}"
    )


@pytest.mark.asyncio
async def test_mock_budget_exhaustion_no_evidence_lost(failed_scripted_inv, db):
    """
    Even a failed investigation must retain whatever evidence was logged
    before the budget ran out (evidence is never rolled back on failure).
    """
    inv_id, _ = failed_scripted_inv
    rows = await db.fetch(
        "SELECT tool_name FROM evidence_items WHERE investigation_id=$1 ORDER BY sequence_num",
        uuid.UUID(inv_id),
    )
    # The scripted fail path calls 6 tools (all except flag_for_review),
    # several of which accept investigation_id and log evidence.
    assert len(rows) >= 1, (
        "Failed investigation should still have partial evidence items logged"
    )


# ---------------------------------------------------------------------------
# SSE stream delivers events during scripted run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_sse_stream_delivers_tool_events(http):
    """
    SSE stream must deliver tool_call, complete/error, and done events
    during a scripted investigation run.
    """
    await _check_scripted_runner_available(http)

    cr = await http.post(f"{APP_URL}/api/investigations", json={"asset_id": "PUMP-01"})
    assert cr.status_code == 200
    inv_id = cr.json()["investigation_id"]

    # Start run + SSE stream concurrently
    rr = await http.post(f"{APP_URL}/api/investigations/{inv_id}/scripted-run")
    assert rr.status_code == 200

    received: list[dict] = []
    async with httpx.AsyncClient(timeout=90) as streaming_client:
        async with streaming_client.stream(
            "GET", f"{APP_URL}/api/investigations/{inv_id}/stream"
        ) as resp:
            assert "text/event-stream" in resp.headers["content-type"]
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    received.append(payload)
                    if payload.get("type") in ("done", "complete", "error"):
                        break

    event_types = {e["type"] for e in received}
    assert "tool_call" in event_types, f"No tool_call events received. Got: {event_types}"
    assert event_types & {"complete", "done", "error"}, f"No terminal event received. Got: {event_types}"


# ---------------------------------------------------------------------------
# Flag-for-review must not be approved by agent (scripted path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_flag_for_review_not_approved_by_agent(scripted_inv, http):
    """
    After scripted run, investigation must be pending_review — never approved.
    The agent (scripted or real) cannot hold the human token.
    """
    inv_id, final_status = scripted_inv
    assert final_status != "approved", (
        "Scripted agent autonomously approved its own finding — security model violated"
    )
    assert final_status == "pending_review"
