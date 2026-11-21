"""
Telemetry and tag health REST API endpoints — Milestone 1.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from db import get_pool

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/telemetry")
async def get_telemetry(
    asset_id: str = Query(..., description="Asset ID, e.g. PUMP-01"),
    tag_name: str = Query(..., description="Tag name, e.g. Temperature_degC"),
    minutes: int = Query(60, ge=1, le=10080, description="Lookback window in minutes"),
):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT timestamp, value, opc_quality_code, opc_quality_label, unit, source
        FROM telemetry
        WHERE asset_id = $1
          AND tag_name = $2
          AND timestamp >= $3
        ORDER BY timestamp ASC
        """,
        asset_id,
        tag_name,
        since,
    )
    return {
        "asset_id": asset_id,
        "tag_name": tag_name,
        "minutes": minutes,
        "is_simulated": True,
        "count": len(rows),
        "readings": [
            {
                "timestamp": r["timestamp"].isoformat(),
                "value": r["value"],
                "opc_quality_code": r["opc_quality_code"],
                "opc_quality_label": r["opc_quality_label"],
                "unit": r["unit"],
                "source": r["source"],
            }
            for r in rows
        ],
    }


@router.get("/tag-health")
async def get_tag_health(asset_id: Optional[str] = Query(None)):
    pool = get_pool()
    if asset_id:
        rows = await pool.fetch(
            """
            SELECT asset_id, tag_name, last_update, freshness_status,
                   staleness_threshold_seconds, updated_at
            FROM tag_health
            WHERE asset_id = $1
            ORDER BY tag_name
            """,
            asset_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT asset_id, tag_name, last_update, freshness_status,
                   staleness_threshold_seconds, updated_at
            FROM tag_health
            ORDER BY asset_id, tag_name
            """
        )
    return {
        "is_simulated": True,
        "tags": [
            {
                "asset_id": r["asset_id"],
                "tag_name": r["tag_name"],
                "last_update": r["last_update"].isoformat() if r["last_update"] else None,
                "freshness_status": r["freshness_status"],
                "staleness_threshold_seconds": r["staleness_threshold_seconds"],
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/alarms")
async def get_alarms(
    asset_id: Optional[str] = Query(None),
    since_minutes: int = Query(60, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    pool = get_pool()

    if asset_id:
        rows = await pool.fetch(
            """
            SELECT alarm_id, asset_id, alarm_type, severity, message,
                   triggered_at, acknowledged_at, raw_value, threshold
            FROM alarms
            WHERE asset_id = $1 AND triggered_at >= $2
            ORDER BY triggered_at DESC
            LIMIT $3
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
            ORDER BY triggered_at DESC
            LIMIT $2
            """,
            since, limit,
        )

    return {
        "is_simulated": True,
        "count": len(rows),
        "alarms": [
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
            }
            for r in rows
        ],
    }


@router.get("/health")
async def health():
    pool = get_pool()
    try:
        await pool.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}
