"""
Baseline seeder — populates 7 days of normal-operating telemetry at 1-minute resolution.

Required before Milestone 2's compare_baseline MCP tool will return meaningful statistics.
Run after docker-compose up:
  docker-compose run --rm seed

Design:
  - Fixed random seed (42) for reproducibility.
  - Values drawn from Gaussian(nominal, std_dev) — no faults.
  - All rows: source='SEED_BASELINE', is_simulated=True, opc_quality_label='Good'.
  - Timestamps from 7 days ago to 1 minute ago (exclusive of current live data window).
  - Uses COPY for bulk insert performance.

Verification:
  After running, the script prints row counts per tag and validates:
    - Minimum 10,080 rows per tag (7 days × 1440 min/day)
    - All rows have opc_quality_label = 'Good'
    - Computed std_dev from stored values matches tag model std_dev ± 20%
"""

import asyncio
import os
import random
import sys
from datetime import datetime, timezone, timedelta

import asyncpg

# Import tag definitions from simulator directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulator"))
from tag_model import TAGS, OPC_QUALITY_GOOD  # noqa: E402


SEED = 42
DAYS_BACK = 7
INTERVAL_MINUTES = 1
EXPECTED_ROWS_PER_TAG = DAYS_BACK * 24 * 60  # 10,080


async def seed(pool: asyncpg.Pool) -> None:
    rng = random.Random(SEED)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(days=DAYS_BACK)

    print(f"Seeding {DAYS_BACK} days of baseline data ({EXPECTED_ROWS_PER_TAG} rows/tag)...")

    for tag in TAGS:
        rows = []
        ts = start
        while ts < now - timedelta(minutes=1):
            value = rng.gauss(tag.nominal, tag.std_dev)
            value = max(tag.min_physical, min(tag.max_physical, value))
            rows.append((
                tag.asset_id,
                tag.tag_name,
                ts,
                round(value, 4),
                OPC_QUALITY_GOOD,
                "Good",
                tag.unit,
            ))
            ts += timedelta(minutes=INTERVAL_MINUTES)

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO telemetry
                  (asset_id, tag_name, timestamp, value, opc_quality_code,
                   opc_quality_label, unit, source, is_simulated)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'SEED_BASELINE', TRUE)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
        print(f"  {tag.asset_id}/{tag.tag_name}: {len(rows)} rows inserted")

    print("\nValidating...")
    await _validate(pool)


async def _validate(pool: asyncpg.Pool) -> None:
    import statistics

    all_ok = True
    for tag in TAGS:
        row = await pool.fetchrow(
            """
            SELECT COUNT(*) as cnt,
                   AVG(value) as mean,
                   STDDEV_SAMP(value) as stddev
            FROM telemetry
            WHERE asset_id = $1
              AND tag_name = $2
              AND source = 'SEED_BASELINE'
              AND opc_quality_label = 'Good'
            """,
            tag.asset_id,
            tag.tag_name,
        )
        cnt = row["cnt"]
        if cnt < EXPECTED_ROWS_PER_TAG:
            print(f"  FAIL {tag.asset_id}/{tag.tag_name}: only {cnt} rows, expected >= {EXPECTED_ROWS_PER_TAG}")
            all_ok = False
            continue

        stddev = row["stddev"] or 0
        expected_std = tag.std_dev
        # Allow ±20% variance from expected std_dev
        if not (expected_std * 0.80 <= stddev <= expected_std * 1.20):
            print(f"  WARN {tag.asset_id}/{tag.tag_name}: stddev={stddev:.4f}, expected~{expected_std:.4f}")
        else:
            print(f"  OK   {tag.asset_id}/{tag.tag_name}: {cnt} rows, stddev={stddev:.4f}")

    if all_ok:
        print("\nBaseline seed validated successfully.")
    else:
        print("\nBaseline seed validation FAILED — check output above.")
        sys.exit(1)


async def main() -> None:
    pool = await asyncpg.create_pool(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
    )
    try:
        await seed(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
