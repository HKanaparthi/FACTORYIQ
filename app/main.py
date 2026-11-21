"""
FactoryIQ app — FastAPI entrypoint for Milestone 1.

Starts two background tasks on startup:
  - MQTT consumer: ingests telemetry from MQTT broker into TimescaleDB
  - Freshness monitor: marks stale tags in tag_health table

Exposes REST endpoints on APP_PORT (default 8000).
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_pool, close_pool
from ingestion.mqtt_consumer import run_consumer
from ingestion.freshness_monitor import run_freshness_monitor
from api.telemetry import router as telemetry_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    logger.info("Database pool initialised")

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
    description="Industrial AI Reliability Testbed — Milestone 1",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry_router)


if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
