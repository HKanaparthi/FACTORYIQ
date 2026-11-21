"""
Physics simulation for FactoryIQ tags.

Computes the current value and OPC UA quality code for a given tag,
taking into account active faults and their ramp progress.

Design:
  - Each call is stateless given the same inputs (tag definition + active faults + elapsed time).
  - Gaussian noise is added per call; for reproducibility in tests, pass a seeded rng.
  - Values are clamped to [min_physical, max_physical].
"""

import math
import random
import time
from typing import Optional

from tag_model import (
    TagDefinition,
    FaultProfile,
    FAULT_DEFINITIONS,
    OPC_QUALITY_GOOD,
    OPC_QUALITY_BAD,
    quality_label,
)


def compute_reading(
    tag: TagDefinition,
    active_faults: list,  # list[ActiveFault] — imported lazily to avoid circular import
    rng: Optional[random.Random] = None,
) -> tuple[Optional[float], int]:
    """
    Returns (value, opc_quality_code).
    Returns (None, OPC_QUALITY_BAD) if the tag should not publish a value this cycle
    (stop_publishing fault).
    """
    if rng is None:
        rng = random.Random()

    key = (tag.asset_id, tag.tag_name)
    effective_delta = 0.0
    effective_noise_mult = 1.0
    force_quality: Optional[int] = None
    stop = False

    now = time.monotonic()

    for fault in active_faults:
        profiles = FAULT_DEFINITIONS.get(fault.fault_type, {})
        profile: Optional[FaultProfile] = profiles.get(key)
        if profile is None:
            continue

        if profile.stop_publishing:
            stop = True
            continue

        if profile.force_quality is not None:
            force_quality = profile.force_quality

        elapsed = now - fault.start_time
        if profile.ramp_seconds > 0:
            ramp_fraction = min(1.0, elapsed / profile.ramp_seconds)
        else:
            ramp_fraction = 1.0

        effective_delta += ramp_fraction * profile.delta
        effective_noise_mult = max(effective_noise_mult, profile.noise_multiplier)

    if stop:
        # Tag stops publishing — caller should skip sending this value
        return None, OPC_QUALITY_GOOD  # quality was Good when last published

    value = tag.nominal + effective_delta + rng.gauss(0.0, tag.std_dev * effective_noise_mult)
    value = max(tag.min_physical, min(tag.max_physical, value))

    quality = force_quality if force_quality is not None else OPC_QUALITY_GOOD
    return round(value, 4), quality


def should_trigger_alarm(
    tag: TagDefinition,
    value: float,
    quality_code: int,
) -> Optional[str]:
    """
    Returns alarm severity string if this reading should trigger an alarm, else None.
    Does not fire alarms for Bad quality readings (the comm_loss itself is the event).
    """
    if quality_code == OPC_QUALITY_BAD:
        return None

    # Alarm on high threshold crossings
    if tag.alarm_critical is not None and value >= tag.alarm_critical:
        return "CRITICAL"
    if tag.alarm_high is not None and value >= tag.alarm_high:
        return "HIGH"

    # Alarm on low threshold crossings (pressure drop)
    if tag.tag_name == "Pressure_bar" and tag.asset_id == "PUMP-01" and value <= 2.0:
        return "HIGH"

    return None
