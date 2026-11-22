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


KNOWN_ASSETS = ["CONVEYOR-01", "FILL-01", "MOTOR-01", "PUMP-01"]

ASSET_META = {
    "PUMP-01":     {"label": "Centrifugal Pump",   "tags": ["Temperature_degC", "Pressure_bar", "Vibration_mm_s", "FlowRate_Lmin"]},
    "MOTOR-01":    {"label": "Electric Motor",      "tags": ["Current_A", "Temperature_degC", "Speed_rpm"]},
    "CONVEYOR-01": {"label": "Conveyor Belt",       "tags": ["Speed_mps", "Temperature_degC"]},
    "FILL-01":     {"label": "Filling Station",     "tags": ["Level_pct", "FillRate_Lmin", "Temperature_degC"]},
}


@router.get("/assets")
async def list_assets():
    """Return all known assets with current tag-health summary, alarm count, and latest investigation."""
    pool = get_pool()

    # Tag health grouped by asset_id
    health_rows = await pool.fetch(
        """
        SELECT asset_id,
               COUNT(*) FILTER (WHERE freshness_status = 'FRESH')   AS fresh,
               COUNT(*) FILTER (WHERE freshness_status = 'STALE')   AS stale,
               COUNT(*) FILTER (WHERE freshness_status = 'MISSING') AS missing,
               COUNT(*)                                               AS total
        FROM tag_health
        GROUP BY asset_id
        """
    )
    health_map = {r["asset_id"]: dict(r) for r in health_rows}

    # Recent alarm counts + max severity (last 60 min)
    alarm_rows = await pool.fetch(
        """
        SELECT asset_id,
               COUNT(*) AS cnt,
               BOOL_OR(severity IN ('HIGH','CRITICAL')) AS has_high
        FROM alarms
        WHERE triggered_at >= NOW() - INTERVAL '60 minutes'
          AND acknowledged_at IS NULL
        GROUP BY asset_id
        """
    )
    alarm_map = {r["asset_id"]: r["cnt"] for r in alarm_rows}
    alarm_high_map = {r["asset_id"]: r["has_high"] for r in alarm_rows}

    # Latest investigation per asset
    inv_rows = await pool.fetch(
        """
        SELECT DISTINCT ON (asset_id)
            asset_id, investigation_id, status
        FROM investigations
        ORDER BY asset_id, started_at DESC
        """
    )
    inv_map = {r["asset_id"]: r for r in inv_rows}

    assets = []
    for asset_id in KNOWN_ASSETS:
        h = health_map.get(asset_id, {"fresh": 0, "stale": 0, "missing": 0, "total": 0})
        inv = inv_map.get(asset_id)
        total = h["total"] or 0
        fresh = h["fresh"] or 0
        stale = h["stale"] or 0
        has_high_alarms = alarm_high_map.get(asset_id, False)
        if total == 0:
            health_status = "UNKNOWN"
        elif stale > 0:
            health_status = "DEGRADED"
        elif has_high_alarms:
            health_status = "WARNING"
        else:
            health_status = "HEALTHY"

        assets.append({
            "asset_id": asset_id,
            "label": ASSET_META[asset_id]["label"],
            "tags": ASSET_META[asset_id]["tags"],
            "health_status": health_status,
            "fresh_tags": int(fresh),
            "stale_tags": int(stale),
            "missing_tags": int(h["missing"] or 0),
            "total_tags": int(total),
            "recent_alarms": int(alarm_map.get(asset_id, 0)),
            "latest_investigation_id": str(inv["investigation_id"]) if inv else None,
            "latest_investigation_status": inv["status"] if inv else None,
        })

    return {"assets": assets}


@router.get("/health")
async def health():
    pool = get_pool()
    try:
        await pool.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}
