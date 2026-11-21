"""
FactoryIQ Simulator — entrypoint.

Runs three concurrent asyncio tasks:
  1. OPC UA server (asyncua) on OPC_UA_PORT
  2. MQTT publisher (aiomqtt) publishing to MQTT_HOST:MQTT_PORT
  3. FastAPI fault injection API on SIMULATOR_PORT

The fault injection API modifies the shared FaultState, which is read by both
the OPC UA server and MQTT publisher on every publish cycle.

Environment variables (all required, sourced from .env):
  OPC_UA_PORT, MQTT_HOST, MQTT_PORT, SIMULATOR_PORT
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from fault_state import FaultState, ActiveFault
from opcua_server import OPCUAServer
from mqtt_publisher import MQTTPublisher
from tag_model import ALLOWED_ASSETS, ALLOWED_FAULT_TYPES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Shared fault state — module-level so API handlers can access it
_fault_state = FaultState()


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------

class InjectFaultRequest(BaseModel):
    asset_id: str
    fault_type: str
    duration_seconds: int = 300

    @field_validator("asset_id")
    @classmethod
    def validate_asset_id(cls, v: str) -> str:
        if v not in ALLOWED_ASSETS:
            raise ValueError(f"Unknown asset_id '{v}'. Allowed: {sorted(ALLOWED_ASSETS)}")
        return v

    @field_validator("fault_type")
    @classmethod
    def validate_fault_type(cls, v: str) -> str:
        if v not in ALLOWED_FAULT_TYPES:
            raise ValueError(f"Unknown fault_type '{v}'. Allowed: {sorted(ALLOWED_FAULT_TYPES)}")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < 0:
            raise ValueError("duration_seconds must be >= 0 (0 = indefinite)")
        return v


class RemoveFaultRequest(BaseModel):
    fault_id: str


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Simulator API ready")
    yield
    logger.info("Simulator API shutting down")


api = FastAPI(
    title="FactoryIQ Simulator",
    description="Fault injection API for the FactoryIQ industrial simulation",
    version="0.1.0",
    lifespan=lifespan,
)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.post("/inject-fault", status_code=200)
async def inject_fault(req: InjectFaultRequest) -> dict:
    import time
    fault = ActiveFault(
        fault_type=req.fault_type,
        asset_id=req.asset_id,
        start_time=time.monotonic(),
        duration_seconds=req.duration_seconds,
        fault_id=str(uuid.uuid4()),
    )
    await _fault_state.inject(fault)
    logger.info("Fault injected: %s on %s for %ds (id=%s)",
                req.fault_type, req.asset_id, req.duration_seconds, fault.fault_id)
    return {
        "fault_id": fault.fault_id,
        "fault_type": req.fault_type,
        "asset_id": req.asset_id,
        "duration_seconds": req.duration_seconds,
    }


@api.delete("/faults/{fault_id}", status_code=200)
async def remove_fault(fault_id: str) -> dict:
    removed = await _fault_state.remove(fault_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Fault {fault_id} not found")
    return {"removed": fault_id}


@api.get("/faults", status_code=200)
async def list_faults() -> dict:
    return {"active_faults": await _fault_state.list_summary()}


@api.get("/health", status_code=200)
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Main — starts all three components concurrently
# ---------------------------------------------------------------------------

async def main() -> None:
    opc_ua_port = int(os.environ.get("OPC_UA_PORT", "4840"))
    mqtt_host = os.environ.get("MQTT_HOST", "mosquitto")
    mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))
    sim_port = int(os.environ.get("SIMULATOR_PORT", "8001"))

    opc_server = OPCUAServer(
        endpoint=f"opc.tcp://0.0.0.0:{opc_ua_port}/factoryiq",
        fault_state=_fault_state,
    )
    mqtt_pub = MQTTPublisher(
        host=mqtt_host,
        port=mqtt_port,
        fault_state=_fault_state,
    )

    config = uvicorn.Config(api, host="0.0.0.0", port=sim_port, log_level="warning")
    server = uvicorn.Server(config)

    logger.info("Starting FactoryIQ simulator: OPC UA :%d, MQTT→%s:%d, API :%d",
                opc_ua_port, mqtt_host, mqtt_port, sim_port)

    await asyncio.gather(
        opc_server.start(),
        mqtt_pub.run(),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
