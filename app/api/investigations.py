"""
Investigation management API — Milestone 2.

Provides endpoints to create investigations and approve/reject findings.
Human approval requires MCP_HUMAN_TOKEN (different from MCP_BEARER_TOKEN).
The AI agent cannot approve its own findings — it only has MCP_BEARER_TOKEN.
"""

import os
import uuid
import logging

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from db import get_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/investigations", tags=["investigations"])

HUMAN_TOKEN: str = os.environ.get("MCP_HUMAN_TOKEN", "human-changeme")


class CreateInvestigationRequest(BaseModel):
    asset_id: str
    trigger_alarm_id: Optional[str] = None


class ApproveRejectRequest(BaseModel):
    notes: Optional[str] = None


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
               started_at, completed_at, is_simulated
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
        "evidence_items": [
            {
                "evidence_id": str(e["evidence_id"]),
                "sequence_num": e["sequence_num"],
                "tool_name": e["tool_name"],
                "tool_inputs": e["tool_inputs"],
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
