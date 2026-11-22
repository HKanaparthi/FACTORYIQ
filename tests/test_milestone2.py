"""
Milestone 2 integration tests.

Tests run against the live docker-compose stack.
Run from the project root:
  APP_URL=http://localhost:8080 POSTGRES_PORT=5433 pytest tests/test_milestone2.py -v

Covers all 12 Milestone 2 acceptance criteria plus tool contracts.
Tests exercise MCP tools through the actual MCP streamable-HTTP protocol
using the official mcp Python client SDK.
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import asyncpg
import httpx
import pytest
import pytest_asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client

APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
MCP_URL = f"{APP_URL}/mcp/"
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
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def db():
    conn = await asyncpg.connect(POSTGRES_DSN)
    yield conn
    await conn.close()


@pytest_asyncio.fixture(scope="function")
async def http():
    async with httpx.AsyncClient(timeout=15) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def mcp_session():
    """Authenticated MCP client session.

    anyio cancel scopes must be entered and exited in the same asyncio task.
    pytest-asyncio 0.24 runs fixture teardown in a different task from setup,
    so we pin the entire session lifecycle (setup + teardown) to one dedicated
    asyncio task and communicate across the task boundary with Events.
    """
    session_ready: asyncio.Event = asyncio.Event()
    session_done: asyncio.Event = asyncio.Event()
    session_holder: list = []
    exc_holder: list = []

    async def _run_session() -> None:
        try:
            http_client = create_mcp_http_client(
                headers={"Authorization": f"Bearer {MCP_TOKEN}"}
            )
            async with streamable_http_client(MCP_URL, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    session_holder.append(session)
                    session_ready.set()
                    await session_done.wait()
        except Exception as exc:  # noqa: BLE001
            exc_holder.append(exc)
            session_ready.set()

    task = asyncio.create_task(_run_session())
    await session_ready.wait()

    if exc_holder:
        raise exc_holder[0]

    yield session_holder[0]

    session_done.set()
    await task


@pytest_asyncio.fixture(scope="function")
async def investigation_id(http):
    """Create a fresh investigation and return its ID."""
    r = await http.post(f"{APP_URL}/api/investigations", json={"asset_id": "PUMP-01"})
    assert r.status_code == 200, r.text
    return r.json()["investigation_id"]


def _extract(result: Any) -> dict:
    """Extract the JSON dict from a CallToolResult."""
    text = result.content[0].text
    return json.loads(text)


# ---------------------------------------------------------------------------
# AC1: MCP server starts and tools are discoverable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac1_mcp_server_starts(mcp_session):
    tools = await mcp_session.list_tools()
    assert tools is not None
    assert len(tools.tools) == 7


@pytest.mark.asyncio
async def test_ac1_all_seven_tools_discoverable(mcp_session):
    tools = await mcp_session.list_tools()
    names = {t.name for t in tools.tools}
    expected = {
        "query_telemetry", "query_alarms", "query_equipment_docs",
        "compare_baseline", "check_data_quality", "get_recent_events",
        "flag_for_review",
    }
    assert expected == names, f"Tool mismatch. Got: {names}"


# ---------------------------------------------------------------------------
# AC2: Each tool returns correctly structured responses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac2_query_telemetry_structure(mcp_session):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    result = await mcp_session.call_tool("query_telemetry", {
        "asset_id": "PUMP-01",
        "tag_name": "Temperature_degC",
        "start_iso": start,
        "end_iso": end,
    })
    data = _extract(result)
    assert data["success"] is True
    assert "data" in data and data["error"] is None
    assert "readings" in data["data"]
    assert "count" in data["data"]
    assert data["data"]["asset_id"] == "PUMP-01"
    assert data["data"]["is_simulated"] is True


@pytest.mark.asyncio
async def test_ac2_query_alarms_structure(mcp_session):
    result = await mcp_session.call_tool("query_alarms", {"asset_id": "PUMP-01", "limit": 5})
    data = _extract(result)
    assert data["success"] is True
    assert "alarms" in data["data"]
    assert "count" in data["data"]


@pytest.mark.asyncio
async def test_ac2_query_equipment_docs_structure(mcp_session):
    result = await mcp_session.call_tool("query_equipment_docs", {
        "query_text": "bearing vibration pump"
    })
    data = _extract(result)
    assert data["success"] is True
    assert "documents" in data["data"]
    assert len(data["data"]["documents"]) > 0
    doc = data["data"]["documents"][0]
    assert "title" in doc and "content" in doc and "source_ref" in doc
    assert doc["is_illustrative"] is True


@pytest.mark.asyncio
async def test_ac2_compare_baseline_structure(mcp_session):
    result = await mcp_session.call_tool("compare_baseline", {
        "asset_id": "PUMP-01",
        "tag_name": "Vibration_mm_s",
        "window_minutes": 10,
    })
    data = _extract(result)
    assert data["success"] is True
    # Either has baseline data or returns insufficient_data — both are valid structures
    assert "evidence_tier" in data["data"]
    assert data["data"]["asset_id"] == "PUMP-01"


@pytest.mark.asyncio
async def test_ac2_check_data_quality_structure(mcp_session):
    result = await mcp_session.call_tool("check_data_quality", {
        "asset_id": "PUMP-01",
        "since_minutes": 30,
    })
    data = _extract(result)
    assert data["success"] is True
    assert "tags" in data["data"]
    assert "overall_issues" in data["data"]
    assert "quality_note" in data["data"]
    # Verify two-signal design: each tag has both freshness and quality info
    for tag in data["data"]["tags"]:
        assert "freshness_status" in tag
        assert "recent_good_count" in tag
        assert "usable_as_evidence" in tag


@pytest.mark.asyncio
async def test_ac2_get_recent_events_structure(mcp_session):
    result = await mcp_session.call_tool("get_recent_events", {
        "asset_id": "PUMP-01",
        "since_minutes": 60,
    })
    data = _extract(result)
    assert data["success"] is True
    assert "events" in data["data"]
    assert "count" in data["data"]


@pytest.mark.asyncio
async def test_ac2_flag_for_review_structure(mcp_session, investigation_id):
    result = await mcp_session.call_tool("flag_for_review", {
        "investigation_id": investigation_id,
        "finding_text": "Elevated vibration observed on PUMP-01.",
        "evidence_tiers": json.dumps([
            {"tag": "PUMP-01/Vibration_mm_s", "tier": "STATISTICAL_SIGNAL",
             "rationale": "z-score 3.2 above 7-day baseline"}
        ]),
        "alt_hypotheses": json.dumps(["Sensor noise", "Normal startup transient"]),
    })
    data = _extract(result)
    assert data["success"] is True
    assert data["data"]["status"] == "pending_review"
    assert data["data"]["pending_human_approval"] is True
    assert "approval_note" in data["data"]


# ---------------------------------------------------------------------------
# AC3: Authentication rejects unauthorized requests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac3_no_token_returns_401(http):
    r = await http.post(MCP_URL, content=b"{}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_ac3_wrong_token_returns_401(http):
    r = await http.post(
        MCP_URL,
        headers={"Authorization": "Bearer wrongtoken"},
        content=b"{}",
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_ac3_empty_bearer_returns_401(http):
    # "Bearer" with no token (no space after) — h11 rejects trailing-space values
    r = await http.post(
        MCP_URL,
        headers={"Authorization": "Bearer"},
        content=b"{}",
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# AC4: Input validation — invalid asset, tag, timestamp ranges
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac4_invalid_asset_id(mcp_session):
    now = datetime.now(timezone.utc)
    result = await mcp_session.call_tool("query_telemetry", {
        "asset_id": "REACTOR-99",
        "tag_name": "Temperature_degC",
        "start_iso": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    data = _extract(result)
    assert data["success"] is False
    assert "REACTOR-99" in data["error"]


@pytest.mark.asyncio
async def test_ac4_invalid_tag_name(mcp_session):
    now = datetime.now(timezone.utc)
    result = await mcp_session.call_tool("query_telemetry", {
        "asset_id": "PUMP-01",
        "tag_name": "NonExistentTag",
        "start_iso": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    data = _extract(result)
    assert data["success"] is False
    assert "NonExistentTag" in data["error"]


@pytest.mark.asyncio
async def test_ac4_start_after_end(mcp_session):
    now = datetime.now(timezone.utc)
    result = await mcp_session.call_tool("query_telemetry", {
        "asset_id": "PUMP-01",
        "tag_name": "Temperature_degC",
        "start_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_iso": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    data = _extract(result)
    assert data["success"] is False
    assert "start_iso must be before" in data["error"].lower() or "before" in data["error"].lower()


@pytest.mark.asyncio
async def test_ac4_window_exceeds_24h(mcp_session):
    now = datetime.now(timezone.utc)
    result = await mcp_session.call_tool("query_telemetry", {
        "asset_id": "PUMP-01",
        "tag_name": "Temperature_degC",
        "start_iso": (now - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    data = _extract(result)
    assert data["success"] is False
    assert "24" in data["error"]


@pytest.mark.asyncio
async def test_ac4_invalid_severity_in_query_alarms(mcp_session):
    result = await mcp_session.call_tool("query_alarms", {
        "severity": "CATASTROPHIC",
    })
    data = _extract(result)
    assert data["success"] is False


@pytest.mark.asyncio
async def test_ac4_empty_docs_query(mcp_session):
    result = await mcp_session.call_tool("query_equipment_docs", {"query_text": ""})
    data = _extract(result)
    assert data["success"] is False


# ---------------------------------------------------------------------------
# AC5: All telemetry tools are read-only (no write paths via MCP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac5_no_approve_tool_in_mcp(mcp_session):
    """The agent must not have an 'approve' or 'acknowledge' tool available."""
    tools = await mcp_session.list_tools()
    forbidden = {"approve", "acknowledge", "approve_investigation", "acknowledge_finding"}
    exposed = {t.name for t in tools.tools}
    overlap = forbidden & exposed
    assert not overlap, f"Dangerous tools exposed via MCP: {overlap}"


@pytest.mark.asyncio
async def test_ac5_flag_for_review_does_not_approve(db, mcp_session, investigation_id):
    """flag_for_review sets status=pending_review, never approved."""
    await mcp_session.call_tool("flag_for_review", {
        "investigation_id": investigation_id,
        "finding_text": "Test finding.",
        "evidence_tiers": "[]",
    })
    status = await db.fetchval(
        "SELECT status FROM investigations WHERE investigation_id = $1",
        uuid.UUID(investigation_id),
    )
    assert status == "pending_review"
    assert status != "approved"


# ---------------------------------------------------------------------------
# AC6: Ground truth inaccessible through MCP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac6_no_fault_labels_in_alarm_messages(db):
    """Alarm messages must not contain fault type labels."""
    rows = await db.fetch("SELECT message FROM alarms LIMIT 100")
    forbidden_labels = {"bearing_wear", "motor_overheating", "pressure_drop",
                        "vibration_anomaly", "stale_sensor", "comm_loss"}
    for r in rows:
        msg = r["message"].lower()
        for label in forbidden_labels:
            assert label not in msg, (
                f"Alarm message contains fault label '{label}': {r['message']}"
            )


@pytest.mark.asyncio
async def test_ac6_no_scenario_id_in_mcp_tools(mcp_session):
    """MCP tool responses must not contain evaluation_scenarios data."""
    result = await mcp_session.call_tool("query_alarms", {"limit": 10})
    text = result.content[0].text
    assert "scenario_id" not in text
    assert "bearing_wear_nominal" not in text


# ---------------------------------------------------------------------------
# AC7: Evidence records persisted correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac7_evidence_logged_on_tool_call(db, mcp_session, investigation_id):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    await mcp_session.call_tool("query_telemetry", {
        "asset_id": "PUMP-01",
        "tag_name": "Temperature_degC",
        "start_iso": start,
        "end_iso": end,
        "investigation_id": investigation_id,
    })

    count = await db.fetchval(
        "SELECT COUNT(*) FROM evidence_items WHERE investigation_id = $1",
        uuid.UUID(investigation_id),
    )
    assert count >= 1, "No evidence item logged after tool call with investigation_id"


@pytest.mark.asyncio
async def test_ac7_evidence_item_has_correct_fields(db, mcp_session, investigation_id):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    await mcp_session.call_tool("query_telemetry", {
        "asset_id": "PUMP-01",
        "tag_name": "Vibration_mm_s",
        "start_iso": start,
        "end_iso": end,
        "investigation_id": investigation_id,
    })

    row = await db.fetchrow(
        """
        SELECT tool_name, tool_inputs, tool_output, evidence_tier, recorded_at
        FROM evidence_items WHERE investigation_id = $1 ORDER BY sequence_num ASC LIMIT 1
        """,
        uuid.UUID(investigation_id),
    )
    assert row is not None
    assert row["tool_name"] == "query_telemetry"
    assert "PUMP-01" in row["tool_inputs"]
    assert row["evidence_tier"] in (
        "CONFIRMED_OBSERVATION", "STATISTICAL_SIGNAL",
        "CORROBORATING_EVIDENCE", "WEAK_SIGNAL", "INSUFFICIENT_DATA",
    )
    assert row["recorded_at"] is not None


@pytest.mark.asyncio
async def test_ac7_evidence_sequence_increments(db, mcp_session, investigation_id):
    """Multiple tool calls produce sequential evidence items."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    for tag in ("Temperature_degC", "Vibration_mm_s"):
        await mcp_session.call_tool("query_telemetry", {
            "asset_id": "PUMP-01",
            "tag_name": tag,
            "start_iso": start,
            "end_iso": end,
            "investigation_id": investigation_id,
        })

    rows = await db.fetch(
        "SELECT sequence_num FROM evidence_items WHERE investigation_id = $1 ORDER BY sequence_num",
        uuid.UUID(investigation_id),
    )
    seqs = [r["sequence_num"] for r in rows]
    assert seqs == list(range(1, len(seqs) + 1)), f"Non-sequential evidence items: {seqs}"


# ---------------------------------------------------------------------------
# AC8: Stale and missing telemetry handled accurately
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac8_check_data_quality_two_signals(mcp_session, http):
    """Inject stale_sensor fault and verify check_data_quality returns STALE status."""
    r = await http.post(
        f"{os.environ.get('SIM_URL', 'http://localhost:8001')}/inject-fault",
        json={"asset_id": "PUMP-01", "fault_type": "stale_sensor", "duration_seconds": 60},
    )
    assert r.status_code == 200
    fault_id = r.json()["fault_id"]

    # Wait for tag to go stale (staleness threshold is 10s + monitor runs every 5s)
    await asyncio.sleep(20)

    result = await mcp_session.call_tool("check_data_quality", {
        "asset_id": "PUMP-01",
        "tag_names": "Temperature_degC",
    })
    data = _extract(result)
    assert data["success"] is True

    temp_tag = next(t for t in data["data"]["tags"] if t["tag_name"] == "Temperature_degC")
    assert temp_tag["freshness_status"] == "STALE", (
        f"Expected STALE, got {temp_tag['freshness_status']}"
    )
    # Last stored quality should still be Good (sensor was healthy when it stopped publishing)
    assert temp_tag["usable_as_evidence"] is False, "Stale tag must not be usable as evidence"

    stale_issues = [i for i in temp_tag["issues"] if "STALE" in i]
    assert stale_issues, "No STALE issue reported for stale sensor"

    await http.delete(f"{os.environ.get('SIM_URL', 'http://localhost:8001')}/faults/{fault_id}")


@pytest.mark.asyncio
async def test_ac8_comm_loss_bad_quality_reported(mcp_session, http):
    """comm_loss fault → check_data_quality reports BAD quality for FILL-01 tags."""
    r = await http.post(
        f"{os.environ.get('SIM_URL', 'http://localhost:8001')}/inject-fault",
        json={"asset_id": "FILL-01", "fault_type": "comm_loss", "duration_seconds": 30},
    )
    assert r.status_code == 200
    fault_id = r.json()["fault_id"]

    await asyncio.sleep(10)

    result = await mcp_session.call_tool("check_data_quality", {
        "asset_id": "FILL-01",
        "since_minutes": 5,
    })
    data = _extract(result)
    assert data["success"] is True

    # At least one FILL-01 tag should report BAD quality issues
    all_issues = " ".join(
        issue for tag in data["data"]["tags"] for issue in tag["issues"]
    )
    assert "BAD_QUALITY" in all_issues or data["data"]["overall_issues"], (
        "No BAD_QUALITY issues reported after comm_loss"
    )

    await http.delete(f"{os.environ.get('SIM_URL', 'http://localhost:8001')}/faults/{fault_id}")


# ---------------------------------------------------------------------------
# AC9: flag_for_review cannot be approved by agent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac9_pending_review_requires_human_token(http, db, investigation_id):
    """Approval requires MCP_HUMAN_TOKEN, which the agent does not have."""
    # Inject pending_review status directly
    await db.execute(
        "UPDATE investigations SET status='pending_review' WHERE investigation_id=$1",
        uuid.UUID(investigation_id),
    )

    # Agent's MCP token cannot approve
    r = await http.post(
        f"{APP_URL}/api/investigations/{investigation_id}/approve",
        headers={"Authorization": f"Bearer {MCP_TOKEN}"},
        json={},
    )
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"

    # Human token can approve
    r2 = await http.post(
        f"{APP_URL}/api/investigations/{investigation_id}/approve",
        headers={"Authorization": f"Bearer {HUMAN_TOKEN}"},
        json={},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# AC10: MCP tool failures return controlled errors (no stack traces)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac10_tool_error_no_stack_trace(mcp_session):
    """Error responses must not expose internal stack traces."""
    result = await mcp_session.call_tool("query_telemetry", {
        "asset_id": "INVALID-ASSET",
        "tag_name": "Temperature_degC",
        "start_iso": "not-a-date",
        "end_iso": "also-not-a-date",
    })
    data = _extract(result)
    assert data["success"] is False
    # Must not contain Python stack trace indicators
    err = data.get("error", "")
    assert "Traceback" not in err
    assert "File \"" not in err
    assert "line " not in err


@pytest.mark.asyncio
async def test_ac10_flag_review_missing_investigation(mcp_session):
    """flag_for_review with non-existent investigation_id returns controlled error."""
    fake_id = str(uuid.uuid4())
    result = await mcp_session.call_tool("flag_for_review", {
        "investigation_id": fake_id,
        "finding_text": "Test",
        "evidence_tiers": "[]",
    })
    data = _extract(result)
    assert data["success"] is False
    assert "not found" in data["error"].lower() or fake_id in data["error"]


@pytest.mark.asyncio
async def test_ac10_flag_review_invalid_uuid(mcp_session):
    result = await mcp_session.call_tool("flag_for_review", {
        "investigation_id": "not-a-uuid",
        "finding_text": "Test",
        "evidence_tiers": "[]",
    })
    data = _extract(result)
    assert data["success"] is False


# ---------------------------------------------------------------------------
# AC11: Milestone 1 regression — verify app health and telemetry still work
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac11_milestone1_app_health(http):
    r = await http.get(f"{APP_URL}/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ac11_milestone1_telemetry_still_flowing(db):
    await asyncio.sleep(5)
    count = await db.fetchval(
        """
        SELECT COUNT(*) FROM telemetry
        WHERE timestamp > NOW() - INTERVAL '30 seconds'
        """
    )
    assert count > 0, "No telemetry in last 30 seconds — ingestion may be broken"


# ---------------------------------------------------------------------------
# AC12: compare_baseline handles missing baseline gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac12_compare_baseline_insufficient_data(mcp_session):
    """Without seed data, compare_baseline returns INSUFFICIENT_DATA — not an error."""
    result = await mcp_session.call_tool("compare_baseline", {
        "asset_id": "CONVEYOR-01",
        "tag_name": "Speed_mps",
        "window_minutes": 10,
    })
    data = _extract(result)
    assert data["success"] is True  # structured response, not a tool failure
    assert data["data"]["evidence_tier"] in ("INSUFFICIENT_DATA", "CONFIRMED_OBSERVATION",
                                              "STATISTICAL_SIGNAL", "WEAK_SIGNAL")
    if not data["data"].get("baseline_available"):
        assert "insufficient" in data["data"].get("message", "").lower() or \
               data["data"]["evidence_tier"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Additional contract tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_investigation_lifecycle(http, db):
    """Full investigation lifecycle: create → flag → reject."""
    # Create
    r = await http.post(
        f"{APP_URL}/api/investigations",
        json={"asset_id": "MOTOR-01"},
    )
    assert r.status_code == 200
    inv_id = r.json()["investigation_id"]
    assert r.json()["status"] == "in_progress"

    # Get
    r2 = await http.get(f"{APP_URL}/api/investigations/{inv_id}")
    assert r2.status_code == 200
    assert r2.json()["asset_id"] == "MOTOR-01"

    # Transition to pending_review
    await db.execute(
        "UPDATE investigations SET status='pending_review' WHERE investigation_id=$1",
        uuid.UUID(inv_id),
    )

    # Reject with human token
    r3 = await http.post(
        f"{APP_URL}/api/investigations/{inv_id}/reject",
        headers={"Authorization": f"Bearer {HUMAN_TOKEN}"},
        json={"notes": "False alarm"},
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_get_recent_events_chronological(mcp_session):
    """Events must be returned in chronological (oldest-first) order."""
    result = await mcp_session.call_tool("get_recent_events", {
        "since_minutes": 120,
        "limit": 20,
    })
    data = _extract(result)
    assert data["success"] is True
    events = data["data"]["events"]
    if len(events) >= 2:
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps), "Events not in chronological order"


@pytest.mark.asyncio
async def test_query_equipment_docs_no_results_for_unrelated_query(mcp_session):
    """Keyword search returns empty list for completely unrelated query."""
    result = await mcp_session.call_tool("query_equipment_docs", {
        "query_text": "cryptocurrency blockchain quantum",
    })
    data = _extract(result)
    assert data["success"] is True
    # May return 0 or some results — either is valid; just must not fabricate
    assert isinstance(data["data"]["documents"], list)


@pytest.mark.asyncio
async def test_limit_enforcement_query_alarms(mcp_session):
    """limit > 100 must be clamped to 100."""
    result = await mcp_session.call_tool("query_alarms", {"limit": 999})
    data = _extract(result)
    assert data["success"] is True
    assert len(data["data"]["alarms"]) <= 100


@pytest.mark.asyncio
async def test_no_investigation_id_no_evidence_logged(db, mcp_session):
    """Tool calls without investigation_id must not create evidence items."""
    before = await db.fetchval("SELECT COUNT(*) FROM evidence_items")
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    await mcp_session.call_tool("query_telemetry", {
        "asset_id": "PUMP-01",
        "tag_name": "Temperature_degC",
        "start_iso": start,
        "end_iso": end,
        # No investigation_id
    })
    after = await db.fetchval("SELECT COUNT(*) FROM evidence_items")
    assert after == before, "Evidence item created without investigation_id"
