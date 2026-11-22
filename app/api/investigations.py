"""
Investigation management API — Milestone 2 + 3.

Milestone 2: Create, list, approve, and reject investigations.
Milestone 3: Trigger AI agent runs (non-blocking) and stream progress via SSE.

Human approval requires MCP_HUMAN_TOKEN (different from MCP_BEARER_TOKEN).
The AI agent cannot approve its own findings — it only has MCP_BEARER_TOKEN.
"""

import asyncio
import json
import os
import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from db import get_pool

# agent.runner imported lazily inside the endpoint to avoid circular imports
# at module load time (agent depends on db which must be initialised first).

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/investigations", tags=["investigations"])

HUMAN_TOKEN: str = os.environ.get("MCP_HUMAN_TOKEN", "human-changeme")

# ---------------------------------------------------------------------------
# In-process SSE event queues: investigation_id → asyncio.Queue
# Queue items are dicts (SSE event payload) or None (end-of-stream sentinel).
# ---------------------------------------------------------------------------
_active_queues: dict[str, asyncio.Queue] = {}


def _get_or_create_queue(investigation_id: str) -> asyncio.Queue:
    if investigation_id not in _active_queues:
        _active_queues[investigation_id] = asyncio.Queue()
    return _active_queues[investigation_id]


def _remove_queue(investigation_id: str) -> None:
    _active_queues.pop(investigation_id, None)


class CreateInvestigationRequest(BaseModel):
    asset_id: str
    trigger_alarm_id: Optional[str] = None


class ApproveRejectRequest(BaseModel):
    notes: Optional[str] = None


class ReviewProxyRequest(BaseModel):
    action: str  # "approve" or "reject"
    notes: Optional[str] = None
    password: str  # validated server-side against MCP_HUMAN_TOKEN


def _require_human_token(authorization: str = "") -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if token != HUMAN_TOKEN:
        raise HTTPException(status_code=403, detail="Human session token required")


@router.post("")
async def create_investigation(body: CreateInvestigationRequest):
    """Create a new investigation. Returns investigation_id for use in MCP tool calls."""
    allowed = {"CONVEYOR-01", "PUMP-01", "MOTOR-01", "FILL-01"}
    if body.asset_id not in allowed:
        raise HTTPException(status_code=422, detail=f"Unknown asset_id '{body.asset_id}'")

    alarm_uuid: Optional[uuid.UUID] = None
    if body.trigger_alarm_id:
        try:
            alarm_uuid = uuid.UUID(body.trigger_alarm_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid trigger_alarm_id UUID")

    pool = get_pool()

    if alarm_uuid:
        exists = await pool.fetchval(
            "SELECT 1 FROM alarms WHERE alarm_id = $1", alarm_uuid
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Alarm not found")

    row = await pool.fetchrow(
        """
        INSERT INTO investigations (asset_id, trigger_alarm_id)
        VALUES ($1, $2)
        RETURNING investigation_id, asset_id, status, started_at
        """,
        body.asset_id, alarm_uuid,
    )
    return {
        "investigation_id": str(row["investigation_id"]),
        "asset_id": row["asset_id"],
        "status": row["status"],
        "started_at": row["started_at"].isoformat(),
    }


@router.get("")
async def list_investigations(status: Optional[str] = None):
    """List investigations, optionally filtered by status."""
    pool = get_pool()
    if status:
        rows = await pool.fetch(
            """
            SELECT investigation_id, asset_id, status, started_at, completed_at,
                   finding_text
            FROM investigations WHERE status = $1 ORDER BY started_at DESC LIMIT 50
            """,
            status,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT investigation_id, asset_id, status, started_at, completed_at,
                   finding_text
            FROM investigations ORDER BY started_at DESC LIMIT 50
            """
        )
    return {
        "count": len(rows),
        "investigations": [
            {
                "investigation_id": str(r["investigation_id"]),
                "asset_id": r["asset_id"],
                "status": r["status"],
                "started_at": r["started_at"].isoformat(),
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
                "has_finding": r["finding_text"] is not None,
            }
            for r in rows
        ],
    }


@router.get("/{investigation_id}")
async def get_investigation(investigation_id: str):
    """Get full investigation detail including evidence items."""
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid investigation_id UUID")

    pool = get_pool()
    inv = await pool.fetchrow(
        """
        SELECT investigation_id, asset_id, trigger_alarm_id, status,
               finding_text, evidence_summary, alt_hypotheses,
               started_at, completed_at, is_simulated,
               agent_model, agent_error, agent_tool_calls
        FROM investigations WHERE investigation_id = $1
        """,
        inv_uuid,
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    evidence = await pool.fetch(
        """
        SELECT evidence_id, sequence_num, tool_name, tool_inputs, tool_output,
               evidence_tier, recorded_at, citation_text
        FROM evidence_items WHERE investigation_id = $1 ORDER BY sequence_num ASC
        """,
        inv_uuid,
    )

    return {
        "investigation_id": str(inv["investigation_id"]),
        "asset_id": inv["asset_id"],
        "trigger_alarm_id": str(inv["trigger_alarm_id"]) if inv["trigger_alarm_id"] else None,
        "status": inv["status"],
        "finding_text": inv["finding_text"],
        "evidence_summary": inv["evidence_summary"],
        "alt_hypotheses": inv["alt_hypotheses"],
        "started_at": inv["started_at"].isoformat(),
        "completed_at": inv["completed_at"].isoformat() if inv["completed_at"] else None,
        "is_simulated": inv["is_simulated"],
        "agent_model": inv["agent_model"],
        "agent_error": inv["agent_error"],
        "agent_tool_calls": inv["agent_tool_calls"],
        "evidence_items": [
            {
                "evidence_id": str(e["evidence_id"]),
                "sequence_num": e["sequence_num"],
                "tool_name": e["tool_name"],
                "tool_inputs": e["tool_inputs"],
                "tool_output": e["tool_output"],
                "evidence_tier": e["evidence_tier"],
                "recorded_at": e["recorded_at"].isoformat(),
                "citation_text": e["citation_text"],
            }
            for e in evidence
        ],
    }


@router.post("/{investigation_id}/approve")
async def approve_investigation(
    investigation_id: str,
    body: ApproveRejectRequest,
    authorization: str = Header(default=""),
):
    """
    Approve a pending finding. Requires human session token (MCP_HUMAN_TOKEN).
    The AI agent does not have this token — it cannot approve its own findings.
    """
    _require_human_token(authorization)

    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid investigation_id UUID")

    pool = get_pool()
    inv = await pool.fetchrow(
        "SELECT status FROM investigations WHERE investigation_id = $1", inv_uuid
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if inv["status"] != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve: investigation status is '{inv['status']}', expected 'pending_review'",
        )

    await pool.execute(
        "UPDATE investigations SET status = 'approved' WHERE investigation_id = $1",
        inv_uuid,
    )
    logger.info("Investigation %s approved by human", investigation_id)
    return {"investigation_id": investigation_id, "status": "approved", "notes": body.notes}


@router.post("/{investigation_id}/reject")
async def reject_investigation(
    investigation_id: str,
    body: ApproveRejectRequest,
    authorization: str = Header(default=""),
):
    """Reject a pending finding. Requires human session token."""
    _require_human_token(authorization)

    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid investigation_id UUID")

    pool = get_pool()
    inv = await pool.fetchrow(
        "SELECT status FROM investigations WHERE investigation_id = $1", inv_uuid
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if inv["status"] != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reject: investigation status is '{inv['status']}'",
        )

    await pool.execute(
        "UPDATE investigations SET status = 'rejected' WHERE investigation_id = $1",
        inv_uuid,
    )
    logger.info("Investigation %s rejected by human", investigation_id)
    return {"investigation_id": investigation_id, "status": "rejected", "notes": body.notes}


# ---------------------------------------------------------------------------
# Human review proxy — MCP_HUMAN_TOKEN lives server-side only
# ---------------------------------------------------------------------------

@router.post("/{investigation_id}/review")
async def review_investigation_proxy(
    investigation_id: str,
    body: ReviewProxyRequest,
):
    """
    Server-side proxy for approve/reject. The frontend sends a password typed by
    the human reviewer; this endpoint validates it against MCP_HUMAN_TOKEN (server-side
    only) so the token never appears in browser code, Vite env vars, or the bundle.
    """
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'reject'")

    if body.password != HUMAN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid review password")

    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid investigation_id UUID")

    pool = get_pool()
    inv = await pool.fetchrow(
        "SELECT status FROM investigations WHERE investigation_id = $1", inv_uuid
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if inv["status"] != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot {body.action}: investigation status is '{inv['status']}'",
        )

    new_status = "approved" if body.action == "approve" else "rejected"
    await pool.execute(
        f"UPDATE investigations SET status = '{new_status}' WHERE investigation_id = $1",
        inv_uuid,
    )
    logger.info("Investigation %s %s via review proxy", investigation_id, new_status)
    return {"investigation_id": investigation_id, "status": new_status, "notes": body.notes}


# ---------------------------------------------------------------------------
# Milestone 3: AI agent trigger + SSE progress stream
# ---------------------------------------------------------------------------

@router.post("/{investigation_id}/run")
async def run_investigation(
    investigation_id: str,
    background_tasks: BackgroundTasks,
):
    """
    Trigger the AI investigation agent for an existing investigation.
    Returns immediately; the agent runs as a background task.
    Stream progress via GET /{investigation_id}/stream.
    """
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid investigation_id UUID")

    pool = get_pool()
    inv = await pool.fetchrow(
        "SELECT asset_id, trigger_alarm_id, status FROM investigations WHERE investigation_id = $1",
        inv_uuid,
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if inv["status"] not in ("in_progress",):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot run agent: investigation status is '{inv['status']}'. "
                "Only 'in_progress' investigations can be started."
            ),
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is not configured — agent unavailable.",
        )

    # Create the SSE queue before starting the task so early SSE connects don't miss events
    queue = _get_or_create_queue(investigation_id)

    # Import here to keep module-load order safe (db pool may not exist at import time)
    from agent.runner import run_investigation as _run  # noqa: PLC0415

    trigger_alarm_id = (
        str(inv["trigger_alarm_id"]) if inv["trigger_alarm_id"] else None
    )

    background_tasks.add_task(
        _run,
        investigation_id,
        inv["asset_id"],
        trigger_alarm_id,
        queue,
    )

    return {
        "investigation_id": investigation_id,
        "status": "running",
        "stream_url": f"/api/investigations/{investigation_id}/stream",
    }


@router.post("/{investigation_id}/scripted-run")
async def scripted_run_investigation(
    investigation_id: str,
    background_tasks: BackgroundTasks,
    fail_before_flag: bool = False,
):
    """
    Deterministic scripted investigation — no Anthropic API call.
    Only available when ALLOW_SCRIPTED_RUNNER=true (dev/test environments).
    Used by regression tests to exercise the full pipeline without API credits.
    """
    if os.environ.get("ALLOW_SCRIPTED_RUNNER", "").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")

    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid investigation_id UUID")

    pool = get_pool()
    inv = await pool.fetchrow(
        "SELECT asset_id, trigger_alarm_id, status FROM investigations WHERE investigation_id = $1",
        inv_uuid,
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if inv["status"] not in ("in_progress",):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot run agent: investigation status is '{inv['status']}'",
        )

    queue = _get_or_create_queue(investigation_id)

    from agent.runner import run_scripted_investigation as _run_scripted  # noqa: PLC0415

    trigger_alarm_id = (
        str(inv["trigger_alarm_id"]) if inv["trigger_alarm_id"] else None
    )

    background_tasks.add_task(
        _run_scripted,
        investigation_id,
        inv["asset_id"],
        trigger_alarm_id,
        queue,
        fail_before_flag,
    )

    return {
        "investigation_id": investigation_id,
        "status": "running",
        "mode": "scripted",
        "stream_url": f"/api/investigations/{investigation_id}/stream",
    }


@router.get("/{investigation_id}/stream")
async def stream_investigation(investigation_id: str):
    """
    Server-Sent Events stream for investigation progress.
    Each event is a JSON-encoded dict with a 'type' field.
    Event types: tool_call, tool_result, warning, complete, error, heartbeat, done.
    Stream closes after the investigation ends (done event) or on client disconnect.
    """
    try:
        uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid investigation_id UUID")

    queue = _get_or_create_queue(investigation_id)

    async def generate():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send heartbeat to keep the connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    continue

                if event is None:
                    # End-of-stream sentinel from the agent runner
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break

                yield f"data: {json.dumps(event)}\n\n"

        except asyncio.CancelledError:
            pass
        finally:
            _remove_queue(investigation_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
