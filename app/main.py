"""
FactoryIQ app — FastAPI entrypoint (Milestone 1 + 2).

Background tasks:
  - MQTT consumer: ingests telemetry from MQTT broker into TimescaleDB
  - Freshness monitor: marks stale tags in tag_health table

Mounted sub-applications:
  - /mcp  — MCP server (streamable HTTP, bearer-token protected)

REST endpoints on APP_PORT (default 8000).
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_pool, close_pool, get_pool
from ingestion.mqtt_consumer import run_consumer
from ingestion.freshness_monitor import run_freshness_monitor
from api.telemetry import router as telemetry_router
from api.investigations import router as investigations_router
from api.evaluation import router as evaluation_router
from mcp_server.server import build_mcp_asgi, MCP_TOKEN, mcp as mcp_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


async def _run_migrations() -> None:
    """Execute Milestone 2+ SQL migration files in order.

    001_initial.sql is skipped — it runs at DB container init via
    docker-entrypoint-initdb.d/ as the postgres superuser (required for
    CREATE EXTENSION timescaledb). Later migrations use only IF NOT EXISTS
    DDL and are safe to run with the factoryiq app user.
    """
    pool = get_pool()
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if sql_file.name == "001_initial.sql":
            continue
        logger.info("Applying migration: %s", sql_file.name)
        sql = sql_file.read_text()
        try:
            await pool.execute(sql)
            logger.info("Migration %s applied", sql_file.name)
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.debug("Migration %s: %s (expected)", sql_file.name, e)
            else:
                logger.exception("Migration %s failed", sql_file.name)
                raise


async def _seed_scenarios() -> None:
    """Upsert all 36 evaluation scenarios and ground truth into eval tables."""
    from evaluation.scenarios import SCENARIOS
    pool = get_pool()
    for s in SCENARIOS:
        gt = s.get("ground_truth", {})
        await pool.execute(
            """
            INSERT INTO eval_scenarios (
                scenario_id, version, name, category, asset_id,
                evidence_condition, description, fault_config, expected_behavior, seed
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (scenario_id) DO UPDATE SET
                version           = EXCLUDED.version,
                name              = EXCLUDED.name,
                description       = EXCLUDED.description,
                fault_config      = EXCLUDED.fault_config,
                expected_behavior = EXCLUDED.expected_behavior
            """,
            s["scenario_id"], s["version"], s["name"], s["category"],
            s["asset_id"], s["evidence_condition"], s["description"],
            s["fault_config"], s["expected_behavior"], s["seed"],
        )
        if gt:
            await pool.execute(
                """
                INSERT INTO eval_ground_truth (
                    scenario_id, true_root_cause, injected_fault_type,
                    acceptable_conclusion_patterns, negative_patterns,
                    uncertainty_required, fault_expected, evaluation_notes
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (scenario_id) DO UPDATE SET
                    true_root_cause                = EXCLUDED.true_root_cause,
                    injected_fault_type            = EXCLUDED.injected_fault_type,
                    acceptable_conclusion_patterns = EXCLUDED.acceptable_conclusion_patterns,
                    negative_patterns              = EXCLUDED.negative_patterns,
                    uncertainty_required           = EXCLUDED.uncertainty_required,
                    fault_expected                 = EXCLUDED.fault_expected,
                    evaluation_notes               = EXCLUDED.evaluation_notes
                """,
                s["scenario_id"],
                gt.get("true_root_cause", "unknown"),
                gt.get("injected_fault_type"),
                gt.get("acceptable_conclusion_patterns", []),
                gt.get("negative_patterns", []),
                gt.get("uncertainty_required", False),
                gt.get("fault_expected", False),
                gt.get("evaluation_notes", ""),
            )
    logger.info("Eval scenarios seeded (%d scenarios)", len(SCENARIOS))


async def _seed_equipment_docs() -> None:
    """Insert corpus documents into equipment_docs if the table is empty."""
    from mcp_server.corpus import CORPUS
    pool = get_pool()
    count = await pool.fetchval("SELECT COUNT(*) FROM equipment_docs")
    if count and count > 0:
        return
    for doc in CORPUS:
        await pool.execute(
            """
            INSERT INTO equipment_docs (asset_type, doc_type, title, content, keywords, source_ref)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            doc["asset_type"],
            doc["doc_type"],
            doc["title"],
            doc["content"],
            doc["keywords"],
            doc["source_ref"],
        )
    logger.info("Equipment docs corpus seeded (%d documents)", len(CORPUS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    logger.info("Database pool initialised")

    await _run_migrations()
    await _seed_equipment_docs()
    await _seed_scenarios()

    # session_manager.run() initialises the anyio task group required by the
    # MCP streamable-HTTP transport.  FastAPI's app.mount() does not propagate
    # lifespan events to sub-apps, so we start it explicitly here.
    async with mcp_server.session_manager.run():
        consumer_task = asyncio.create_task(run_consumer(), name="mqtt_consumer")
        freshness_task = asyncio.create_task(run_freshness_monitor(), name="freshness_monitor")
        logger.info("Background tasks started")

        yield

        consumer_task.cancel()
        freshness_task.cancel()
        await asyncio.gather(consumer_task, freshness_task, return_exceptions=True)

    await close_pool()
    logger.info("App shutdown complete")


app = FastAPI(
    title="FactoryIQ API",
    description="Industrial AI Reliability Testbed",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry_router)
app.include_router(investigations_router)
app.include_router(evaluation_router)

# Mount MCP server at /mcp — bearer-token protected via BearerAuthASGI middleware
app.mount("/mcp", build_mcp_asgi(MCP_TOKEN))


if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
