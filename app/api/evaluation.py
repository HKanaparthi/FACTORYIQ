"""
FactoryIQ Milestone 5 — Evaluation API routes.

GET  /api/eval/scenarios                 — list all 36 public scenarios
GET  /api/eval/scenarios/{scenario_id}   — single public scenario
POST /api/eval/runs                      — start a benchmark run (requires ALLOW_SCRIPTED_RUNNER)
GET  /api/eval/runs                      — list recent runs (last 20)
GET  /api/eval/runs/{run_id}             — run status + verdict summary
GET  /api/eval/runs/{run_id}/results     — per-scenario results
GET  /api/eval/four-conditions           — FC-001..FC-004 side-by-side view

Ground truth is never returned by any endpoint here.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_pool
from evaluation.scenarios import (
    FOUR_CONDITION_IDS,
    SCENARIOS,
    get_public_scenario,
    get_scenario,
)
from evaluation.runner import run_benchmark

router = APIRouter(prefix="/api/eval", tags=["evaluation"])

ALLOW_SCRIPTED_RUNNER = os.environ.get("ALLOW_SCRIPTED_RUNNER", "false").lower() == "true"


def _require_runner() -> None:
    if not ALLOW_SCRIPTED_RUNNER:
        raise HTTPException(
            status_code=403,
            detail=(
                "Evaluation runner is disabled. "
                "Set ALLOW_SCRIPTED_RUNNER=true in your .env to enable."
            ),
        )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@router.get("/scenarios")
async def list_scenarios() -> list[dict]:
    return [get_public_scenario(s) for s in SCENARIOS]


@router.get("/scenarios/{scenario_id}")
async def get_scenario_endpoint(scenario_id: str) -> dict:
    s = get_scenario(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id!r} not found")
    return get_public_scenario(s)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


class StartRunRequest(BaseModel):
    scenario_ids: list[str] | None = Field(
        None,
        description="Scenario IDs to run. null = all 36 scenarios.",
    )
    trial_count: int = Field(1, ge=1, le=5, description="Trials per scenario (max 5)")
    adapter_type: str = Field("scripted", description="Must be 'scripted'")


@router.post("/runs", status_code=202)
async def start_run(
    body: StartRunRequest,
    _: None = Depends(_require_runner),
) -> dict[str, Any]:
    if body.adapter_type != "scripted":
        raise HTTPException(status_code=400, detail="adapter_type must be 'scripted'")

    if body.scenario_ids is not None:
        unknown = [sid for sid in body.scenario_ids if get_scenario(sid) is None]
        if unknown:
            raise HTTPException(
                status_code=400, detail=f"Unknown scenario IDs: {unknown}"
            )

    try:
        run_id = await run_benchmark(
            scenario_ids=body.scenario_ids,
            trial_count=body.trial_count,
            adapter_type=body.adapter_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run_id": run_id, "status": "running"}


@router.get("/runs")
async def list_runs() -> list[dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT run_id, adapter_type, trial_count, status, scenario_ids,
               started_at, completed_at, total_scenarios, completed_scenarios,
               error_message
        FROM eval_runs
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    return [dict(r) for r in rows]


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id UUID format")

    pool = get_pool()
    run = await pool.fetchrow(
        """
        SELECT run_id, adapter_type, trial_count, status, scenario_ids,
               started_at, completed_at, total_scenarios, completed_scenarios,
               error_message
        FROM eval_runs WHERE run_id = $1
        """,
        run_uuid,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    summary = await pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE er.diagnostic_verdict = 'correct')           AS correct,
            COUNT(*) FILTER (WHERE er.diagnostic_verdict = 'incorrect')         AS incorrect,
            COUNT(*) FILTER (WHERE er.diagnostic_verdict = 'acceptable_alt')    AS acceptable_alt,
            COUNT(*) FILTER (WHERE er.diagnostic_verdict = 'uncertain_correct') AS uncertain_correct,
            COUNT(*) FILTER (WHERE er.diagnostic_verdict = 'non_evaluable')     AS non_evaluable,
            COUNT(*) FILTER (WHERE er.completed = TRUE)                         AS completed_count,
            COUNT(ers.id)                                                        AS total_rows
        FROM eval_run_scenarios ers
        LEFT JOIN eval_results er ON er.run_scenario_id = ers.id
        WHERE ers.run_id = $1
        """,
        run_uuid,
    )

    return {**dict(run), "summary": dict(summary) if summary else {}}


@router.get("/runs/{run_id}/results")
async def get_run_results(run_id: str) -> list[dict[str, Any]]:
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id UUID format")

    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT
            ers.id              AS run_scenario_id,
            ers.scenario_id,
            ers.trial_num,
            ers.status          AS run_status,
            ers.investigation_id,
            ers.started_at,
            ers.completed_at,
            ers.error_message   AS run_error,
            er.diagnostic_verdict,
            er.evidence_grounded,
            er.uncertainty_handled,
            er.tool_use_ok,
            er.completed,
            er.score_detail,
            er.failure_reason,
            er.evaluated_at
        FROM eval_run_scenarios ers
        LEFT JOIN eval_results er ON er.run_scenario_id = ers.id
        WHERE ers.run_id = $1
        ORDER BY ers.started_at ASC NULLS LAST
        """,
        run_uuid,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Four-condition comparison
# ---------------------------------------------------------------------------


@router.get("/four-conditions")
async def four_conditions_view() -> dict[str, Any]:
    """Public metadata and latest results for FC-001 through FC-004."""
    scenarios_data = [
        get_public_scenario(s)
        for sid in FOUR_CONDITION_IDS
        if (s := get_scenario(sid))
    ]

    pool = get_pool()
    latest_results: dict[str, Any] = {}
    for sid in FOUR_CONDITION_IDS:
        row = await pool.fetchrow(
            """
            SELECT
                er.diagnostic_verdict, er.evidence_grounded,
                er.uncertainty_handled, er.completed,
                er.score_detail, er.failure_reason,
                ers.investigation_id, ers.completed_at
            FROM eval_run_scenarios ers
            JOIN eval_results er ON er.run_scenario_id = ers.id
            WHERE ers.scenario_id = $1
            ORDER BY ers.completed_at DESC NULLS LAST
            LIMIT 1
            """,
            sid,
        )
        if row:
            latest_results[sid] = dict(row)

    return {"scenarios": scenarios_data, "latest_results": latest_results}
