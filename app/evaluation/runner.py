"""
FactoryIQ Milestone 5 — Benchmark Runner.

Orchestrates multi-scenario evaluation runs:
  1. Create eval_runs record and immediately return run_id
  2. Background task: for each scenario × trial —
       a. inject fault via simulator HTTP API (capturing fault_id for cleanup)
       b. create investigation row
       c. run adapter (scripted by default)
       d. evaluate via engine
       e. clean up fault via DELETE /faults/{fault_id}
  3. Mark run completed/failed on finish

CONCURRENCY: only one run is allowed at a time. Starting a second run while
one is running returns a 409 error from the API layer.

FAULT CLEANUP: inject-fault returns a fault_id. The fault is cleared via
DELETE /faults/{fault_id} in the finally block. If cleanup fails, a warning
is logged but the trial is not failed.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from db import get_pool

logger = logging.getLogger(__name__)

SIMULATOR_URL = os.environ.get("SIMULATOR_URL", "http://localhost:8001")


async def _inject_fault(fault_config: dict) -> str | None:
    """
    POST fault injection to simulator.
    Returns the fault_id string (for later cleanup), or None if no fault injected.
    Raises httpx.HTTPError on failure.
    """
    if not fault_config or not fault_config.get("fault_type"):
        return None
    payload = {
        "asset_id": fault_config["asset_id"],
        "fault_type": fault_config["fault_type"],
        "duration_seconds": fault_config.get("duration_seconds", 300),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{SIMULATOR_URL}/inject-fault", json=payload)
        resp.raise_for_status()
        body = resp.json()
        fault_id: str = body["fault_id"]

    wait = fault_config.get("wait_seconds", 6)
    if wait > 0:
        await asyncio.sleep(wait)
    return fault_id


async def _clear_fault(fault_id: str) -> None:
    """
    DELETE /faults/{fault_id} on the simulator. Best-effort: logs on failure,
    never raises so the trial outcome is not affected by cleanup errors.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.delete(f"{SIMULATOR_URL}/faults/{fault_id}")
            if resp.status_code not in (200, 404):
                logger.warning("Unexpected status %d clearing fault %s", resp.status_code, fault_id)
    except Exception as exc:
        logger.warning("Could not clear fault %s: %s", fault_id, exc)


async def _create_investigation(asset_id: str) -> str:
    """Insert a new investigation row and return investigation_id as str."""
    pool = get_pool()
    inv_id: uuid.UUID = await pool.fetchval(
        """
        INSERT INTO investigations (asset_id, status)
        VALUES ($1, 'in_progress')
        RETURNING investigation_id
        """,
        asset_id,
    )
    return str(inv_id)


async def run_benchmark(
    scenario_ids: list[str] | None,
    trial_count: int,
    adapter_type: str,
) -> str:
    """
    Create a benchmark run record and kick off the background task.
    Returns run_id. Raises ValueError if another run is already running.
    """
    from evaluation.scenarios import SCENARIOS

    pool = get_pool()

    # Concurrency guard: only one run at a time
    running_count = await pool.fetchval(
        "SELECT COUNT(*) FROM eval_runs WHERE status = 'running'"
    )
    if running_count and running_count > 0:
        raise ValueError(
            "A benchmark run is already in progress. Wait for it to complete or "
            "cancel it before starting a new one."
        )

    if scenario_ids:
        scenarios = [s for s in SCENARIOS if s["scenario_id"] in scenario_ids]
    else:
        scenarios = list(SCENARIOS)

    total = len(scenarios) * trial_count

    run_id: uuid.UUID = await pool.fetchval(
        """
        INSERT INTO eval_runs (
            adapter_type, trial_count, status,
            scenario_ids, started_at, total_scenarios
        )
        VALUES ($1, $2, 'running', $3, $4, $5)
        RETURNING run_id
        """,
        adapter_type,
        trial_count,
        [s["scenario_id"] for s in scenarios] if scenario_ids else None,
        datetime.now(timezone.utc),
        total,
    )
    run_id_str = str(run_id)

    asyncio.create_task(
        _run_benchmark_task(run_id_str, scenarios, trial_count, adapter_type),
        name=f"eval_{run_id_str[:8]}",
    )
    return run_id_str


async def _run_benchmark_task(
    run_id: str,
    scenarios: list[dict],
    trial_count: int,
    adapter_type: str,
) -> None:
    from evaluation.adapters import get_adapter

    pool = get_pool()
    run_uuid = uuid.UUID(run_id)
    completed = 0

    try:
        adapter = get_adapter(adapter_type)
    except ValueError as exc:
        await _fail_run(run_id, str(exc))
        return

    for scenario in scenarios:
        for trial in range(1, trial_count + 1):
            await _run_single_trial(
                run_id=run_id,
                scenario=scenario,
                trial_num=trial,
                adapter=adapter,
            )
            completed += 1
            await pool.execute(
                "UPDATE eval_runs SET completed_scenarios = $2 WHERE run_id = $1",
                run_uuid, completed,
            )

    await pool.execute(
        """
        UPDATE eval_runs
        SET status = 'completed', completed_at = $2, completed_scenarios = $3
        WHERE run_id = $1
        """,
        run_uuid,
        datetime.now(timezone.utc),
        completed,
    )
    logger.info("Benchmark run %s completed: %d scenarios done", run_id[:8], completed)


async def _run_single_trial(
    run_id: str,
    scenario: dict,
    trial_num: int,
    adapter: Any,
) -> None:
    from evaluation.engine import evaluate_investigation

    pool = get_pool()
    run_uuid = uuid.UUID(run_id)
    scenario_id = scenario["scenario_id"]
    asset_id = scenario["asset_id"]
    fault_config: dict = scenario.get("fault_config", {})

    rs_uuid: uuid.UUID = await pool.fetchval(
        """
        INSERT INTO eval_run_scenarios
            (run_id, scenario_id, trial_num, status, started_at)
        VALUES ($1, $2, $3, 'running', $4)
        RETURNING id
        """,
        run_uuid, scenario_id, trial_num, datetime.now(timezone.utc),
    )
    rs_id = str(rs_uuid)
    fault_id: str | None = None
    investigation_id: str | None = None

    try:
        # 1. Inject fault — capture fault_id for cleanup
        fault_id = await _inject_fault(fault_config)

        # 2. Create investigation
        investigation_id = await _create_investigation(asset_id)

        # 3. Link investigation to run_scenario
        await pool.execute(
            "UPDATE eval_run_scenarios SET investigation_id = $2 WHERE id = $1",
            rs_uuid, uuid.UUID(investigation_id),
        )

        # 4. Run adapter (scripted: deterministic, no paid API)
        await adapter.run(
            investigation_id=investigation_id,
            asset_id=asset_id,
            event_queue=None,
        )

        # 5. Evaluate result
        await evaluate_investigation(
            run_scenario_id=rs_id,
            investigation_id=investigation_id,
            scenario_id=scenario_id,
        )

        await pool.execute(
            """
            UPDATE eval_run_scenarios
            SET status = 'completed', completed_at = $2
            WHERE id = $1
            """,
            rs_uuid, datetime.now(timezone.utc),
        )

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Trial %s/%d failed: %s", scenario_id, trial_num, error_msg)
        await pool.execute(
            """
            UPDATE eval_run_scenarios
            SET status = 'failed', completed_at = $2, error_message = $3
            WHERE id = $1
            """,
            rs_uuid, datetime.now(timezone.utc), error_msg,
        )

    finally:
        # Always attempt to clear the injected fault by its specific fault_id
        if fault_id is not None:
            await _clear_fault(fault_id)


async def _fail_run(run_id: str, error_msg: str) -> None:
    pool = get_pool()
    await pool.execute(
        """
        UPDATE eval_runs
        SET status = 'failed', error_message = $2, completed_at = $3
        WHERE run_id = $1
        """,
        uuid.UUID(run_id), error_msg, datetime.now(timezone.utc),
    )
