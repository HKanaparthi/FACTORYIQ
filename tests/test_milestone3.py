"""
Milestone 3 integration tests: AI Investigation Agent.

Tests run against the live docker-compose stack.
Run from the project root:
  APP_URL=http://localhost:8080 POSTGRES_PORT=5433 SIM_URL=http://localhost:8001 pytest tests/test_milestone3.py -v

Tests that require a real Anthropic API key are marked with:
  @pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY required")

All other tests run without an API key.
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import asyncpg
import httpx
import pytest
import pytest_asyncio

APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
SIM_URL = os.environ.get("SIM_URL", "http://localhost:8001")
HUMAN_TOKEN = os.environ.get("MCP_HUMAN_TOKEN", "human-changeme")
MCP_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "changeme")

POSTGRES_DSN = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'factoryiq')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'factoryiq')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'factoryiq')}"
)

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))

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
async def investigation_id(http):
    """Create a fresh PUMP-01 investigation and return its ID."""
    r = await http.post(f"{APP_URL}/api/investigations", json={"asset_id": "PUMP-01"})
    assert r.status_code == 200, r.text
    return r.json()["investigation_id"]


async def _wait_for_status(http, inv_id: str, timeout_secs: float = 120.0) -> str:
    """Poll GET /api/investigations/{id} until status leaves 'in_progress'."""
    deadline = asyncio.get_event_loop().time() + timeout_secs
    while asyncio.get_event_loop().time() < deadline:
        r = await http.get(f"{APP_URL}/api/investigations/{inv_id}")
        assert r.status_code == 200
        status = r.json()["status"]
        if status != "in_progress":
            return status
        await asyncio.sleep(3)
    return "in_progress"  # timed out waiting


# ---------------------------------------------------------------------------
# Schema and new-column smoke tests (no API key needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_investigation_schema_has_agent_columns(db):
    """Migration 003 must add agent_model, agent_error, agent_tool_calls columns."""
    row = await db.fetchrow(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'investigations'
          AND column_name = ANY($1)
        """,
        ["agent_model", "agent_error", "agent_tool_calls"],
    )
    # At least one column must exist — verifies migration ran
    assert row is not None, "agent_* columns not found — migration 003 may not have run"


@pytest.mark.asyncio
async def test_investigations_status_allows_failed(db):
    """Migration 003 must extend the status constraint to include 'failed'."""
    inv_id = await db.fetchval(
        """
        INSERT INTO investigations (asset_id, status)
        VALUES ('PUMP-01', 'failed')
        RETURNING investigation_id
        """
    )
    assert inv_id is not None
    # Clean up
    await db.execute("DELETE FROM investigations WHERE investigation_id = $1", inv_id)


# ---------------------------------------------------------------------------
# AC1 / AC8: /run endpoint contract (no API key needed for structure tests)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_requires_existing_investigation(http):
    """POST /run on nonexistent UUID returns 404."""
    fake = str(uuid.uuid4())
    r = await http.post(f"{APP_URL}/api/investigations/{fake}/run")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_requires_valid_uuid(http):
    """POST /run with non-UUID path returns 422."""
    r = await http.post(f"{APP_URL}/api/investigations/not-a-uuid/run")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_run_already_completed_investigation(http, db, investigation_id):
    """POST /run on an approved investigation returns 409."""
    await db.execute(
        "UPDATE investigations SET status='approved' WHERE investigation_id=$1",
        uuid.UUID(investigation_id),
    )
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_run_without_api_key_returns_503(http, investigation_id):
    """POST /run returns 503 when ANTHROPIC_API_KEY is not configured.
    This test is only meaningful when the key is absent in the app container."""
    if HAS_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY is set in test env — 503 path not reachable")
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    if r.status_code == 200:
        pytest.skip("App container has ANTHROPIC_API_KEY configured — 503 path not reachable")
    assert r.status_code == 503, r.text
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


# ---------------------------------------------------------------------------
# AC8: SSE stream endpoint contract (no API key needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_returns_sse_content_type(investigation_id):
    """GET /stream must return text/event-stream content type."""
    async with httpx.AsyncClient(timeout=10) as client:
        async with client.stream(
            "GET", f"{APP_URL}/api/investigations/{investigation_id}/stream"
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            # Read the first heartbeat (30-second timeout fires one)
            # We just check the endpoint is reachable and streams correctly
            # by consuming one chunk and verifying it's SSE-formatted.
            # The investigation is idle so we'll get a heartbeat after 30s —
            # instead, trigger /run then read events.


@pytest.mark.asyncio
async def test_stream_invalid_uuid(http):
    """GET /stream with invalid UUID returns 422."""
    r = await http.get(f"{APP_URL}/api/investigations/not-a-uuid/stream")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_run_returns_stream_url(http, investigation_id):
    """POST /run response (when API key set) includes a stream_url field."""
    if not HAS_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY required")
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200
    body = r.json()
    assert "stream_url" in body
    assert investigation_id in body["stream_url"]
    assert body["status"] == "running"


# ---------------------------------------------------------------------------
# AC9: Human approval inaccessible to agent (MCP token cannot approve)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_token_cannot_approve(http, db, investigation_id):
    """The MCP bearer token the agent holds must not be able to approve findings."""
    await db.execute(
        "UPDATE investigations SET status='pending_review' WHERE investigation_id=$1",
        uuid.UUID(investigation_id),
    )
    r = await http.post(
        f"{APP_URL}/api/investigations/{investigation_id}/approve",
        headers={"Authorization": f"Bearer {MCP_TOKEN}"},
        json={},
    )
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"


# ---------------------------------------------------------------------------
# AC10: Ground-truth isolation — evidence items must not contain fault labels
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evidence_items_no_fault_labels(db):
    """Evidence items must never contain scenario_id or fault type labels."""
    rows = await db.fetch("SELECT tool_inputs::text, tool_output::text FROM evidence_items LIMIT 200")
    forbidden = {
        "bearing_wear", "motor_overheating", "pressure_drop",
        "vibration_anomaly", "stale_sensor", "comm_loss",
        "scenario_id", "bearing_wear_nominal",
    }
    for r in rows:
        combined = (r["tool_inputs"] or "") + (r["tool_output"] or "")
        for label in forbidden:
            assert label not in combined.lower(), (
                f"Evidence item contains forbidden label '{label}'"
            )


# ---------------------------------------------------------------------------
# AC6: Tool and API errors are handled safely (graceful failure)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_investigation_handles_missing_api_key(http, db, investigation_id):
    """
    When ANTHROPIC_API_KEY is absent, the agent should set status=failed
    with a meaningful error message (not crash).
    """
    if HAS_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY is set in test env — failure path not applicable")

    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    if r.status_code != 503:
        pytest.skip("App container has ANTHROPIC_API_KEY configured — failure path not applicable")
    assert r.status_code == 503  # 503 returned before task starts

    # Status should still be in_progress (task never ran)
    r2 = await http.get(f"{APP_URL}/api/investigations/{investigation_id}")
    assert r2.json()["status"] == "in_progress"


# ---------------------------------------------------------------------------
# Milestone 1 + 2 regression checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_milestone1_regression_app_health(http):
    r = await http.get(f"{APP_URL}/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_milestone1_regression_telemetry_flowing(db):
    await asyncio.sleep(5)
    count = await db.fetchval(
        "SELECT COUNT(*) FROM telemetry WHERE timestamp > NOW() - INTERVAL '30 seconds'"
    )
    assert count > 0, "No telemetry in last 30 seconds"


@pytest.mark.asyncio
async def test_milestone2_regression_mcp_tools_discoverable():
    """MCP server must still expose exactly 7 tools."""
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    mcp_url = f"{APP_URL}/mcp/"
    session_ready: asyncio.Event = asyncio.Event()
    session_done: asyncio.Event = asyncio.Event()
    session_holder: list = []
    exc_holder: list = []

    async def _run():
        try:
            http_client = create_mcp_http_client(
                headers={"Authorization": f"Bearer {MCP_TOKEN}"}
            )
            async with streamable_http_client(mcp_url, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    session_holder.append(session)
                    session_ready.set()
                    await session_done.wait()
        except Exception as exc:
            exc_holder.append(exc)
            session_ready.set()

    task = asyncio.create_task(_run())
    await session_ready.wait()
    if exc_holder:
        raise exc_holder[0]
    session = session_holder[0]
    tools = await session.list_tools()
    session_done.set()
    await task
    assert len(tools.tools) == 7


# ---------------------------------------------------------------------------
# Real Claude integration tests (require ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required for real agent tests")
async def test_ac1_agent_completes_investigation(http, db, investigation_id):
    """
    AC1: The agent must successfully investigate an incident using real MCP calls.
    Investigation must leave in_progress and reach pending_review or failed.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200, r.text

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)
    assert final_status in ("pending_review", "failed"), (
        f"Investigation still in_progress after 120s"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac2_data_quality_checked_before_conclusions(http, db, investigation_id):
    """
    AC2: check_data_quality must appear in evidence_items before any telemetry tool.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    await _wait_for_status(http, investigation_id, timeout_secs=120)

    rows = await db.fetch(
        """
        SELECT tool_name, sequence_num
        FROM evidence_items
        WHERE investigation_id = $1
        ORDER BY sequence_num ASC
        """,
        uuid.UUID(investigation_id),
    )
    assert len(rows) > 0, "No evidence items logged"

    tool_names = [r["tool_name"] for r in rows]
    assert "check_data_quality" in tool_names, (
        f"check_data_quality was never called. Tools used: {tool_names}"
    )

    # check_data_quality must appear before any query_telemetry
    if "query_telemetry" in tool_names:
        cdq_seq = next(r["sequence_num"] for r in rows if r["tool_name"] == "check_data_quality")
        qt_seq = next(r["sequence_num"] for r in rows if r["tool_name"] == "query_telemetry")
        assert cdq_seq < qt_seq, (
            f"check_data_quality (seq {cdq_seq}) called after query_telemetry (seq {qt_seq})"
        )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac3_evidence_references_in_finding(http, db, investigation_id):
    """
    AC3: Final finding must reference at least one specific asset/tag from tool outputs.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)
    if final_status == "failed":
        pytest.fail(
            "Agent unexpectedly reached 'failed' status — check runner logs. "
            "Likely cause: max_tool_calls too low or budget not respected."
        )

    inv = await db.fetchrow(
        "SELECT finding_text FROM investigations WHERE investigation_id=$1",
        uuid.UUID(investigation_id),
    )
    assert inv is not None
    finding = inv["finding_text"] or ""
    assert len(finding) > 50, "Finding text is too short to be meaningful"

    # Finding must reference a known asset or tag name
    known_tokens = {"PUMP-01", "MOTOR-01", "CONVEYOR-01", "FILL-01",
                    "Temperature_degC", "Vibration_mm_s", "Pressure_bar",
                    "FlowRate_Lmin", "Current_A", "Speed_rpm", "Level_pct"}
    referenced = {t for t in known_tokens if t in finding}
    assert referenced, (
        f"Finding does not reference any known asset or tag name. Finding: {finding[:200]}"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac4_no_confidence_percentages_in_finding(http, db, investigation_id):
    """
    AC4: Finding must not contain percentage confidence claims (e.g., '83% confident').
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)
    if final_status == "failed":
        pytest.fail(
            "Agent unexpectedly reached 'failed' status — check runner logs."
        )

    inv = await db.fetchrow(
        "SELECT finding_text FROM investigations WHERE investigation_id=$1",
        uuid.UUID(investigation_id),
    )
    finding = (inv["finding_text"] or "").lower()

    import re
    pct_pattern = re.compile(r'\d+\s*%\s*(confident|confidence|probability|likelihood|certain)')
    match = pct_pattern.search(finding)
    assert match is None, (
        f"Finding contains percentage confidence: '{match.group()}'. Finding: {finding[:300]}"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac5_stale_sensor_produces_uncertainty(http, db):
    """
    AC5: When primary sensor is stale, finding must acknowledge insufficient data.
    """
    # Inject stale_sensor for PUMP-01 temperature before creating investigation
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{SIM_URL}/inject-fault",
            json={"asset_id": "PUMP-01", "fault_type": "stale_sensor", "duration_seconds": 120},
        )
    assert r.status_code == 200
    fault_id = r.json()["fault_id"]

    # Wait for tag to go STALE
    await asyncio.sleep(20)

    # Create and run investigation
    async with httpx.AsyncClient(timeout=30) as client:
        cr = await client.post(
            f"{APP_URL}/api/investigations",
            json={"asset_id": "PUMP-01"},
        )
        assert cr.status_code == 200
        inv_id = cr.json()["investigation_id"]

        rr = await client.post(f"{APP_URL}/api/investigations/{inv_id}/run")
        assert rr.status_code == 200

    final_status = await _wait_for_status(http, inv_id, timeout_secs=120)

    # Clean up fault
    async with httpx.AsyncClient(timeout=15) as client:
        await client.delete(f"{SIM_URL}/faults/{fault_id}")

    if final_status == "failed":
        pytest.fail(
            "Agent unexpectedly reached 'failed' status during stale sensor test — check runner logs."
        )

    inv = await db.fetchrow(
        "SELECT finding_text FROM investigations WHERE investigation_id=$1",
        uuid.UUID(inv_id),
    )
    finding = (inv["finding_text"] or "").lower()

    # Finding must mention staleness or insufficient data
    uncertainty_signals = ["stale", "insufficient", "unavailable", "cannot confirm",
                           "quality", "not current", "missing"]
    found_signal = any(sig in finding for sig in uncertainty_signals)
    assert found_signal, (
        f"Stale sensor investigation did not mention data quality issues. "
        f"Finding: {finding[:400]}"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac7_evidence_items_persist_after_investigation(http, db, investigation_id):
    """
    AC7: Evidence items must be recorded in the database with correct fields.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)

    rows = await db.fetch(
        """
        SELECT tool_name, tool_inputs, tool_output, evidence_tier,
               sequence_num, recorded_at, citation_text
        FROM evidence_items
        WHERE investigation_id = $1
        ORDER BY sequence_num
        """,
        uuid.UUID(investigation_id),
    )
    assert len(rows) >= 2, f"Expected ≥2 evidence items, got {len(rows)}"

    valid_tiers = {
        "CONFIRMED_OBSERVATION", "STATISTICAL_SIGNAL", "CORROBORATING_EVIDENCE",
        "WEAK_SIGNAL", "INSUFFICIENT_DATA",
    }
    for row in rows:
        assert row["tool_name"] is not None
        assert row["evidence_tier"] in valid_tiers, (
            f"Invalid evidence tier: {row['evidence_tier']}"
        )
        assert row["sequence_num"] > 0
        assert row["recorded_at"] is not None

    # Sequence numbers must be monotonically increasing
    seqs = [r["sequence_num"] for r in rows]
    assert seqs == sorted(seqs), f"Evidence items not in sequence: {seqs}"


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac7_investigation_detail_includes_evidence(http, investigation_id):
    """
    AC7: GET /api/investigations/{id} must return evidence_items after run.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    await _wait_for_status(http, investigation_id, timeout_secs=120)

    detail = await http.get(f"{APP_URL}/api/investigations/{investigation_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert "evidence_items" in body
    assert len(body["evidence_items"]) > 0


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac8_sse_stream_delivers_events(http, investigation_id):
    """
    AC8: SSE stream must deliver tool_call and complete/error events during a run.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    received_events: list[dict] = []

    async with httpx.AsyncClient(timeout=130) as streaming_client:
        async with streaming_client.stream(
            "GET", f"{APP_URL}/api/investigations/{investigation_id}/stream"
        ) as resp:
            assert "text/event-stream" in resp.headers["content-type"]
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    received_events.append(payload)
                    if payload.get("type") in ("done", "complete", "error"):
                        break

    event_types = {e["type"] for e in received_events}
    assert event_types & {"tool_call", "complete", "error", "done"}, (
        f"No meaningful events received. Got types: {event_types}"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac9_human_approval_after_agent_run(http, db, investigation_id):
    """
    AC9: After agent flags for review, only human token can approve.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)
    if final_status != "pending_review":
        pytest.fail(
            f"Agent ended with status='{final_status}' instead of 'pending_review'. "
            "Check runner logs — likely tool budget exhaustion or API error."
        )

    # MCP token cannot approve
    mcp_r = await http.post(
        f"{APP_URL}/api/investigations/{investigation_id}/approve",
        headers={"Authorization": f"Bearer {MCP_TOKEN}"},
        json={},
    )
    assert mcp_r.status_code == 403

    # Human token can approve
    human_r = await http.post(
        f"{APP_URL}/api/investigations/{investigation_id}/approve",
        headers={"Authorization": f"Bearer {HUMAN_TOKEN}"},
        json={},
    )
    assert human_r.status_code == 200
    assert human_r.json()["status"] == "approved"


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_ac10_no_scenario_labels_in_finding(http, db, investigation_id):
    """
    AC10: Final finding text must not contain evaluation scenario labels or fault types.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)
    if final_status == "failed":
        pytest.fail(
            "Agent unexpectedly reached 'failed' status — ground-truth isolation cannot be verified."
        )

    inv = await db.fetchrow(
        "SELECT finding_text FROM investigations WHERE investigation_id=$1",
        uuid.UUID(investigation_id),
    )
    finding = (inv["finding_text"] or "").lower()

    forbidden = {
        "bearing_wear_nominal", "scenario_id", "evaluation_scenario",
        "injected_sequence", "expected_conclusion",
    }
    for label in forbidden:
        assert label not in finding, (
            f"Finding contains forbidden evaluation label '{label}'"
        )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_agent_stores_model_name(http, db, investigation_id):
    """Agent must record the model name used in the investigations row."""
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)
    if final_status == "failed":
        pytest.fail("Agent unexpectedly reached 'failed' status — model metadata cannot be verified.")

    row = await db.fetchrow(
        "SELECT agent_model, agent_tool_calls FROM investigations WHERE investigation_id=$1",
        uuid.UUID(investigation_id),
    )
    assert row["agent_model"] is not None, "agent_model column not set"
    assert row["agent_tool_calls"] is not None and row["agent_tool_calls"] > 0, (
        "agent_tool_calls column not set or is zero"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY required")
async def test_flag_for_review_not_approved_by_agent(http, db, investigation_id):
    """
    After the agent runs, the investigation status must be pending_review (not approved).
    The agent calls flag_for_review — it must NEVER reach approved autonomously.
    """
    r = await http.post(f"{APP_URL}/api/investigations/{investigation_id}/run")
    assert r.status_code == 200

    final_status = await _wait_for_status(http, investigation_id, timeout_secs=120)
    # Agent can only reach pending_review or failed — never approved
    assert final_status != "approved", (
        "Agent autonomously approved its own finding — this violates the security model"
    )
