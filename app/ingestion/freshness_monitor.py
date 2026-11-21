"""
Freshness monitor — background task that marks tags STALE when their last_update
exceeds the staleness threshold.

This is the second, independent data-quality signal:
  - opc_quality_label: reported by the device (last value in telemetry table)
  - freshness_status:  computed here, based on elapsed time since last update

A tag can be opc_quality_label=Good AND freshness_status=STALE.
This is the stale_sensor fault scenario: the device was healthy when it last
published, but it has since stopped publishing.
"""

import asyncio
import logging
import os

from db import get_pool

logger = logging.getLogger(__name__)

CHECK_INTERVAL_S = 5.0  # run every 5 seconds


async def run_freshness_monitor() -> None:
    threshold = int(os.environ.get("TAG_STALENESS_THRESHOLD_SECONDS", "10"))

    while True:
        await asyncio.sleep(CHECK_INTERVAL_S)
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                updated = await conn.execute(
                    """
                    UPDATE tag_health
                    SET freshness_status = 'STALE',
                        updated_at = NOW()
                    WHERE freshness_status = 'FRESH'
                      AND last_update < NOW() - ($1 || ' seconds')::INTERVAL
                    """,
                    str(threshold),
                )
                if updated != "UPDATE 0":
                    logger.info("Freshness monitor: marked tags STALE — %s", updated)
        except Exception:
            logger.exception("Freshness monitor error (non-fatal, will retry)")
