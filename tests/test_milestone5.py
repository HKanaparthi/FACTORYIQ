"""
Milestone 5 — Evaluation Harness tests.

Tests are grouped into:
  1. Scenario Library — structure, ground-truth isolation, count
  2. Evaluation Engine — scoring logic (unit tests with mocked DB)
  3. Ground-Truth Leakage — ground truth never reaches public API
  4. Run Lifecycle — start run, poll status, fetch results (integration, requires stack)
  5. Security — ALLOW_SCRIPTED_RUNNER gate, ground truth absent from scenario endpoint

Integration tests require the Docker stack (APP_URL, POSTGRES_PORT env).
Unit tests run standalone (no stack needed).

Run all:
  APP_URL=http://localhost:8080 POSTGRES_PORT=5433 pytest test_milestone5.py -v

Run unit only (no stack):
  pytest test_milestone5.py -v -m "not integration"
"""

from __future__ import annotations

import os
import re
import sys
import uuid

import pytest

# Allow running from the tests/ directory or repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
POSTGRES_DSN = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'factoryiq')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'factoryiq')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'factoryiq')}"
)

# ---------------------------------------------------------------------------
# 1. Scenario Library unit tests
# ---------------------------------------------------------------------------


def test_scenario_count():
    from evaluation.scenarios import SCENARIOS
    assert len(SCENARIOS) == 36, f"Expected 36 scenarios, got {len(SCENARIOS)}"


def test_scenario_ids_unique():
    from evaluation.scenarios import SCENARIOS
    ids = [s["scenario_id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"


def test_all_scenarios_have_required_fields():
    from evaluation.scenarios import SCENARIOS
    required = {"scenario_id", "version", "name", "category", "asset_id",
                "evidence_condition", "description", "fault_config",
                "expected_behavior", "seed"}
    for s in SCENARIOS:
        missing = required - s.keys()
        assert not missing, f"{s['scenario_id']} missing fields: {missing}"


def test_categories_valid():
    from evaluation.scenarios import SCENARIOS
    valid = {
        "equipment_fault", "evidence_quality", "connectivity",
        "investigation_failure", "safety_ambiguity", "four_condition",
    }
    for s in SCENARIOS:
        assert s["category"] in valid, f"{s['scenario_id']} has invalid category {s['category']!r}"


def test_evidence_conditions_valid():
    from evaluation.scenarios import SCENARIOS
    valid = {"NOMINAL", "NOMINAL_FAULT", "DEGRADED", "DEGRADED_MISSING",
             "CONTRADICTORY", "WRONG_ASSET"}
    for s in SCENARIOS:
        assert s["evidence_condition"] in valid, (
            f"{s['scenario_id']} has invalid evidence_condition {s['evidence_condition']!r}"
        )


def test_ground_truth_present_for_all_scenarios():
    from evaluation.scenarios import SCENARIOS
    for s in SCENARIOS:
        gt = s.get("ground_truth")
        assert gt is not None, f"{s['scenario_id']} missing ground_truth"
        assert "true_root_cause" in gt, f"{s['scenario_id']} ground_truth missing true_root_cause"
        assert "acceptable_conclusion_patterns" in gt
        assert isinstance(gt["acceptable_conclusion_patterns"], list)


def test_ground_truth_stripped_by_get_public_scenario():
    from evaluation.scenarios import SCENARIOS, get_public_scenario
    for s in SCENARIOS:
        public = get_public_scenario(s)
        assert "ground_truth" not in public, (
            f"get_public_scenario leaked ground_truth for {s['scenario_id']}"
        )


def test_four_condition_ids():
    from evaluation.scenarios import FOUR_CONDITION_IDS, get_scenario
    assert FOUR_CONDITION_IDS == ["FC-001", "FC-002", "FC-003", "FC-004"]
    for sid in FOUR_CONDITION_IDS:
        s = get_scenario(sid)
        assert s is not None, f"{sid} not found in SCENARIOS"
        assert s["category"] == "four_condition"


def test_description_does_not_leak_fault_type():
    """Public description must not use the exact fault_type key string from fault_config."""
    from evaluation.scenarios import SCENARIOS
    for s in SCENARIOS:
        fault_type = s.get("fault_config", {}).get("fault_type", "")
        if not fault_type:
            continue
        # Exact fault_type string (e.g. "vibration_spike", "pressure_drop") must not
        # appear verbatim in the description — that would leak ground truth.
        desc_lower = s["description"].lower()
        readable = fault_type.replace("_", " ")  # "vibration spike", "pressure drop"
        assert readable not in desc_lower, (
            f"{s['scenario_id']} description contains exact fault_type text "
            f"{readable!r} — ground-truth leak"
        )


def test_eqf_001_fault_config():
    from evaluation.scenarios import get_scenario
    s = get_scenario("EQF-001")
    assert s is not None
    assert s["fault_config"]["fault_type"] == "pressure_drop"
    assert s["fault_config"]["asset_id"] == "PUMP-01"


def test_eqf_008_no_fault():
    from evaluation.scenarios import get_scenario
    s = get_scenario("EQF-008")
    assert s is not None
    assert s["fault_config"] == {}
    assert s["evidence_condition"] == "NOMINAL"


def test_detection_gap_scenarios_have_no_positive_patterns():
    """EQF-002 through EQF-007 are detection-gap scenarios — no positive patterns."""
    from evaluation.scenarios import get_scenario
    gap_ids = ["EQF-002", "EQF-003", "EQF-004", "EQF-005", "EQF-006", "EQF-007"]
    for sid in gap_ids:
        s = get_scenario(sid)
        assert s is not None
        gt = s["ground_truth"]
        assert gt["acceptable_conclusion_patterns"] == [], (
            f"{sid} should have no positive patterns (detection gap)"
        )


def test_uncertainty_required_scenarios():
    """Evidence quality and stale scenarios should require uncertainty acknowledgment."""
    from evaluation.scenarios import SCENARIOS
    for s in SCENARIOS:
        gt = s["ground_truth"]
        cond = s["evidence_condition"]
        if cond in ("DEGRADED", "DEGRADED_MISSING"):
            assert gt.get("uncertainty_required") is True, (
                f"{s['scenario_id']} has DEGRADED condition but uncertainty_required=False"
            )


# ---------------------------------------------------------------------------
# 2. Evaluation Engine unit tests (pure logic, no DB)
# ---------------------------------------------------------------------------


def test_matches_any_positive():
    from evaluation.engine import _matches_any
    assert _matches_any("pressure anomaly detected", [r"pressure.*anomal"]) is True


def test_matches_any_negative():
    from evaluation.engine import _matches_any
    assert _matches_any("nominal operation", [r"pressure.*anomal"]) is False


def test_matches_any_case_insensitive():
    from evaluation.engine import _matches_any
    assert _matches_any("PRESSURE ANOMALY", [r"pressure.*anomal"]) is True


# ---------------------------------------------------------------------------
# 3. Adapter unit tests
# ---------------------------------------------------------------------------


def test_scripted_adapter_type():
    from evaluation.adapters import ScriptedAdapter
    assert ScriptedAdapter().adapter_type == "scripted"


def test_live_adapter_raises_without_env(monkeypatch):
    monkeypatch.delenv("ALLOW_LIVE_EVAL", raising=False)
    from evaluation.adapters import get_adapter
    with pytest.raises(ValueError, match="disabled"):
        get_adapter("live")


def test_recorded_adapter_raises():
    from evaluation.adapters import get_adapter
    with pytest.raises(ValueError, match="not yet implemented"):
        get_adapter("recorded")


def test_unknown_adapter_raises():
    from evaluation.adapters import get_adapter
    with pytest.raises(ValueError, match="Unknown adapter_type"):
        get_adapter("ai_magic")


def test_get_adapter_scripted_returns_scripted():
    from evaluation.adapters import get_adapter, ScriptedAdapter
    a = get_adapter("scripted")
    assert isinstance(a, ScriptedAdapter)


# ---------------------------------------------------------------------------
# 4. Integration tests — require running Docker stack
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenarios_api_returns_36():
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{APP_URL}/api/eval/scenarios")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 36


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scenario_api_no_ground_truth_leakage():
    """GET /api/eval/scenarios must never return ground_truth field."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{APP_URL}/api/eval/scenarios")
    assert r.status_code == 200
    for s in r.json():
        assert "ground_truth" not in s, (
            f"Scenario {s.get('scenario_id')} leaked ground_truth via API"
        )
        assert "acceptable_conclusion_patterns" not in s
        assert "negative_patterns" not in s
        assert "true_root_cause" not in s


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ground_truth_not_in_db_query_via_public_api():
    """eval_ground_truth table must not be reachable from any public eval endpoint."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        # Scenario endpoint — no gt fields
        r = await client.get(f"{APP_URL}/api/eval/scenarios/EQF-001")
    assert r.status_code == 200
    body = r.json()
    for forbidden in ("true_root_cause", "acceptable_conclusion_patterns",
                      "negative_patterns", "injected_fault_type", "ground_truth"):
        assert forbidden not in body, f"Field {forbidden!r} leaked in scenario response"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_run_requires_allow_scripted_runner():
    """POST /api/eval/runs returns 403 when ALLOW_SCRIPTED_RUNNER=false."""
    import httpx
    # This test verifies the gate. If the env flag is set to true in the running
    # stack, we skip rather than fail — the gate is correctly disabled in prod.
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{APP_URL}/api/eval/runs",
            json={"trial_count": 1, "adapter_type": "scripted"},
        )
    if r.status_code == 403:
        assert "ALLOW_SCRIPTED_RUNNER" in r.json()["detail"]
    elif r.status_code == 202:
        # Runner was enabled — that's fine in a local dev environment
        pytest.skip("ALLOW_SCRIPTED_RUNNER=true in this environment — gate test not applicable")
    else:
        pytest.fail(f"Unexpected status: {r.status_code} {r.text}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_four_conditions_endpoint():
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{APP_URL}/api/eval/four-conditions")
    assert r.status_code == 200
    body = r.json()
    assert "scenarios" in body
    assert "latest_results" in body
    assert len(body["scenarios"]) == 4
    for s in body["scenarios"]:
        assert "ground_truth" not in s
        assert "true_root_cause" not in s


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runs_list_endpoint():
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{APP_URL}/api/eval/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_not_found_returns_404():
    import httpx
    fake_id = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{APP_URL}/api/eval/runs/{fake_id}")
    assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ground_truth_in_db_not_accessible():
    """Directly query DB: eval_ground_truth rows must exist but not be reachable via API."""
    import asyncpg
    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM eval_ground_truth")
        assert count == 36, f"Expected 36 ground truth rows, got {count}"

        # Verify that none of the ground-truth pattern data can be inferred
        # from the eval_scenarios table (the public table)
        columns = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'eval_scenarios'
            """
        )
        col_names = {r["column_name"] for r in columns}
        assert "acceptable_conclusion_patterns" not in col_names
        assert "negative_patterns" not in col_names
        assert "true_root_cause" not in col_names
    finally:
        await conn.close()
