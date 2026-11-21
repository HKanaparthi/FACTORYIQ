"""
Tag definitions for the FactoryIQ simulation.

Each asset has a set of tags with nominal operating ranges and fault profiles.
Fault profiles define how a tag's value changes when a fault is active, using
a ramp model: immediate (ramp_seconds=0) or gradual (ramp_seconds > 0).

OPC UA quality codes follow the OPC UA specification:
  Good      = 0x00000000
  Bad       = 0x80000000
  Uncertain = 0x40000000
"""

from dataclasses import dataclass, field
from typing import Optional


OPC_QUALITY_GOOD = 0x00000000
OPC_QUALITY_BAD = 0x80000000
OPC_QUALITY_UNCERTAIN = 0x40000000


def quality_label(code: int) -> str:
    if code == OPC_QUALITY_GOOD:
        return "Good"
    elif code == OPC_QUALITY_BAD:
        return "Bad"
    elif code == OPC_QUALITY_UNCERTAIN:
        return "Uncertain"
    # OPC UA sub-codes: top 2 bits determine severity
    top = code >> 30
    if top == 0:
        return "Good"
    elif top == 1:
        return "Uncertain"
    else:
        return "Bad"


@dataclass
class TagDefinition:
    asset_id: str
    tag_name: str
    unit: str
    nominal: float          # normal operating value
    std_dev: float          # Gaussian noise standard deviation
    min_physical: float     # physical lower bound (clamp)
    max_physical: float     # physical upper bound (clamp)
    alarm_high: Optional[float] = None   # threshold for HIGH alarm
    alarm_critical: Optional[float] = None


@dataclass
class FaultProfile:
    """
    How a fault affects a specific tag.
    delta: steady-state shift from nominal (signed)
    ramp_seconds: seconds to ramp to full delta (0 = immediate)
    stop_publishing: if True, tag stops emitting values (stale_sensor fault)
    force_quality: if set, overrides quality code for all published values
    noise_multiplier: multiplies std_dev (vibration anomaly uses higher noise)
    """
    delta: float = 0.0
    ramp_seconds: float = 0.0
    stop_publishing: bool = False
    force_quality: Optional[int] = None
    noise_multiplier: float = 1.0


# ISA-95 naming: Enterprise/Site/Area/Line/<AssetID>/<TagName>
ASSET_PATH_PREFIX = "FactoryIQ/CharlotteSite/ProductionArea/Line1"

TAGS: list[TagDefinition] = [
    # --- CONVEYOR-01 ---
    TagDefinition("CONVEYOR-01", "Speed_mps",       "m/s",  1.2,  0.02, 0.0,  3.0,  alarm_high=2.5),
    TagDefinition("CONVEYOR-01", "Temperature_degC","degC", 42.0, 0.5,  10.0, 100.0, alarm_high=75.0, alarm_critical=90.0),

    # --- PUMP-01 ---
    TagDefinition("PUMP-01", "Temperature_degC", "degC",  65.0, 0.8,  10.0, 150.0, alarm_high=90.0,  alarm_critical=110.0),
    TagDefinition("PUMP-01", "Pressure_bar",     "bar",   4.5,  0.05, 0.0,  10.0,  alarm_high=7.0),
    TagDefinition("PUMP-01", "Vibration_mm_s",   "mm/s",  2.1,  0.15, 0.0,  30.0,  alarm_high=8.5,   alarm_critical=15.0),
    TagDefinition("PUMP-01", "FlowRate_Lmin",    "L/min", 120.0,1.5,  0.0,  300.0),

    # --- MOTOR-01 ---
    TagDefinition("MOTOR-01", "Current_A",        "A",    12.5, 0.2,  0.0,  50.0,  alarm_high=20.0,  alarm_critical=28.0),
    TagDefinition("MOTOR-01", "Temperature_degC", "degC", 70.0, 1.0,  10.0, 180.0, alarm_high=100.0, alarm_critical=130.0),
    TagDefinition("MOTOR-01", "Speed_rpm",        "rpm",  1450.0,5.0, 0.0,  2000.0),

    # --- FILL-01 ---
    TagDefinition("FILL-01", "Level_pct",     "%",    68.0, 0.5,  0.0,  100.0, alarm_high=90.0),
    TagDefinition("FILL-01", "FillRate_Lmin", "L/min",85.0, 1.0,  0.0,  200.0),
    TagDefinition("FILL-01", "Temperature_degC","degC",22.0, 0.3,  5.0,  60.0),
]

# Index for O(1) lookups
TAGS_BY_KEY: dict[tuple[str, str], TagDefinition] = {
    (t.asset_id, t.tag_name): t for t in TAGS
}

ALLOWED_ASSETS: set[str] = {t.asset_id for t in TAGS}
ASSET_TAGS: dict[str, list[str]] = {}
for t in TAGS:
    ASSET_TAGS.setdefault(t.asset_id, []).append(t.tag_name)

# ---------------------------------------------------------------------------
# Fault definitions
# Key: fault_type string
# Value: dict mapping (asset_id, tag_name) → FaultProfile
#
# Alarm messages describe observable SYMPTOMS only — never the fault label.
# ---------------------------------------------------------------------------
FAULT_DEFINITIONS: dict[str, dict[tuple[str, str], FaultProfile]] = {
    "bearing_wear": {
        # Gradual vibration increase + slow temperature rise over 10 minutes
        ("PUMP-01", "Vibration_mm_s"):   FaultProfile(delta=+8.5,  ramp_seconds=600, noise_multiplier=2.0),
        ("PUMP-01", "Temperature_degC"): FaultProfile(delta=+22.0, ramp_seconds=720),
    },
    "motor_overheating": {
        # Gradual temperature increase + current rise
        ("MOTOR-01", "Temperature_degC"): FaultProfile(delta=+55.0, ramp_seconds=480),
        ("MOTOR-01", "Current_A"):        FaultProfile(delta=+8.0,  ramp_seconds=300),
    },
    "pressure_drop": {
        # Immediate pressure and flow drop
        ("PUMP-01", "Pressure_bar"):    FaultProfile(delta=-3.5, ramp_seconds=0),
        ("PUMP-01", "FlowRate_Lmin"):   FaultProfile(delta=-65.0, ramp_seconds=0),
    },
    "vibration_anomaly": {
        # Conveyor speed instability with high noise
        ("CONVEYOR-01", "Speed_mps"): FaultProfile(delta=0.0, ramp_seconds=0, noise_multiplier=8.0),
    },
    "stale_sensor": {
        # Pump temperature sensor stops publishing. Last value retains Good quality.
        # The ingestion freshness_monitor will mark it STALE after the threshold.
        ("PUMP-01", "Temperature_degC"): FaultProfile(stop_publishing=True),
    },
    "comm_loss": {
        # All FILL-01 tags publish with Bad quality code
        ("FILL-01", "Level_pct"):       FaultProfile(force_quality=OPC_QUALITY_BAD),
        ("FILL-01", "FillRate_Lmin"):   FaultProfile(force_quality=OPC_QUALITY_BAD),
        ("FILL-01", "Temperature_degC"):FaultProfile(force_quality=OPC_QUALITY_BAD),
    },
}

ALLOWED_FAULT_TYPES: set[str] = set(FAULT_DEFINITIONS.keys())

# Alarm thresholds map: when a tag crosses alarm_high, fire an alarm.
# Message uses symptom language only — no fault type labels.
ALARM_MESSAGES: dict[tuple[str, str], str] = {
    ("PUMP-01",   "Vibration_mm_s"):    "PUMP-01 vibration exceeded threshold",
    ("PUMP-01",   "Temperature_degC"):  "PUMP-01 temperature exceeded threshold",
    ("MOTOR-01",  "Temperature_degC"):  "MOTOR-01 temperature exceeded threshold",
    ("MOTOR-01",  "Current_A"):         "MOTOR-01 current draw exceeded threshold",
    ("PUMP-01",   "Pressure_bar"):      "PUMP-01 pressure dropped below threshold",
    ("CONVEYOR-01","Speed_mps"):        "CONVEYOR-01 speed exceeded threshold",
    ("FILL-01",   "Level_pct"):         "FILL-01 level exceeded threshold",
}
