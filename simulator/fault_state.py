"""
Thread-safe (asyncio) fault state shared between OPC UA server and MQTT publisher.

An active fault has a start_time used to compute the ramp fraction:
  ramp_fraction = min(1.0, elapsed_seconds / ramp_seconds)
  effective_delta = ramp_fraction * fault_profile.delta
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActiveFault:
    fault_type: str
    asset_id: str
    start_time: float           # time.monotonic() at injection
    duration_seconds: int       # 0 = indefinite
    fault_id: str               # UUID for tracking


class FaultState:
    """
    Stores active faults. All public methods are safe to call from asyncio tasks.
    Uses an asyncio.Lock to protect concurrent reads/writes.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: dict[str, ActiveFault] = {}   # fault_id → ActiveFault

    async def inject(self, fault: ActiveFault) -> None:
        async with self._lock:
            self._active[fault.fault_id] = fault

    async def remove(self, fault_id: str) -> bool:
        async with self._lock:
            return self._active.pop(fault_id, None) is not None

    async def get_active(self) -> list[ActiveFault]:
        async with self._lock:
            now = time.monotonic()
            expired = [
                fid for fid, f in self._active.items()
                if f.duration_seconds > 0 and (now - f.start_time) >= f.duration_seconds
            ]
            for fid in expired:
                del self._active[fid]
            return list(self._active.values())

    async def list_summary(self) -> list[dict]:
        faults = await self.get_active()
        now = time.monotonic()
        return [
            {
                "fault_id": f.fault_id,
                "fault_type": f.fault_type,
                "asset_id": f.asset_id,
                "elapsed_seconds": round(now - f.start_time, 1),
                "duration_seconds": f.duration_seconds,
                "remaining_seconds": (
                    max(0, f.duration_seconds - (now - f.start_time))
                    if f.duration_seconds > 0
                    else None
                ),
            }
            for f in faults
        ]
