"""
FactoryIQ Milestone 5 — Scenario Library.

36 versioned industrial reliability scenarios across 6 categories.

DESIGN CONSTRAINTS:
- description field never mentions the injected fault type (ground-truth isolation)
- ground_truth is kept in a separate sub-dict; it is seeded into eval_ground_truth
  which is never accessible via MCP tools or public APIs
- fault_config describes what fault to inject (or {} for no injection)
- evaluation_notes documents limitations honestly

EVALUATION LIMITATIONS (documented here, not hidden):
  The evaluation engine uses pattern matching against the finding text.
  It cannot verify semantic support of claims, only keyword presence.
  Any result labelled non_evaluable requires human review.
  Scripted-runner results must NOT be presented as Claude model accuracy.
"""

from __future__ import annotations

from typing import Any


def _s(
    sid: str,
    name: str,
    cat: str,
    asset: str,
    cond: str,
    desc: str,
    fault: dict,
    expected: dict,
    gt: dict,
    seed: int = 42,
    version: str = "1.0",
) -> dict[str, Any]:
    """Helper to build a scenario dict."""
    return {
        "scenario_id": sid,
        "version": version,
        "name": name,
        "category": cat,
        "asset_id": asset,
        "evidence_condition": cond,
        "description": desc,
        "fault_config": fault,
        "expected_behavior": expected,
        "seed": seed,
        "ground_truth": gt,
    }


# ---------------------------------------------------------------------------
# Convenience defaults
# ---------------------------------------------------------------------------

def _gt(
    root_cause: str,
    patterns: list[str],
    negative: list[str] | None = None,
    uncertainty: bool = False,
    fault_expected: bool = False,
    fault_type: str | None = None,
    notes: str = "",
) -> dict:
    return {
        "true_root_cause": root_cause,
        "injected_fault_type": fault_type,
        "acceptable_conclusion_patterns": patterns,
        "negative_patterns": negative or [],
        "uncertainty_required": uncertainty,
        "fault_expected": fault_expected,
        "evaluation_notes": notes,
    }


PRESSURE_ANOMALY_PATTERNS = [
    r"pressure.*anomal",
    r"low.*pressure",
    r"abnormal.*pressure",
    r"pressure.*deviat",
    r"pressure.*condition",
    r"pressure.*low",
]

NOMINAL_PATTERNS = [
    r"no clear anomal",
    r"within.*normal",
    r"nominal",
    r"does not show.*anomal",
]

UNCERTAINTY_PATTERNS_NEG = [
    r"confirm.*fault",
    r"definit.*anomal",
]

STALE_CAVEAT_PATTERNS = [
    r"stale",
    r"freshness",
    r"not.*fresh",
    r"quality.*issue",
    r"data.*unavail",
    r"cannot.*confirm",
]

QUALITY_CAVEAT_PATTERNS = [
    r"quality",
    r"stale",
    r"unavail",
    r"insufficient",
    r"missing",
    r"bad.*quality",
    r"non.*good",
]


# ---------------------------------------------------------------------------
# 1. Equipment Fault Scenarios (EQF-001 … EQF-008)
#    Focus: can the agent detect known equipment failures?
# ---------------------------------------------------------------------------

EQF_001 = _s(
    "EQF-001",
    "PUMP-01 Pressure Drop — Active Fault, Fresh Data",
    "equipment_fault", "PUMP-01", "NOMINAL_FAULT",
    (
        "PUMP-01 is experiencing a pressure reduction. All sensors are reporting fresh, "
        "valid readings. The investigation should identify the pressure deviation and "
        "recommend inspection without overconfident claims."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "pressure_drop",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": True,
        "should_acknowledge_uncertainty": False,
        "should_complete": True,
        "required_tools": ["check_data_quality", "query_telemetry", "flag_for_review"],
    },
    gt=_gt(
        "pressure_drop_fault",
        PRESSURE_ANOMALY_PATTERNS,
        negative=NOMINAL_PATTERNS,
        fault_expected=True,
        fault_type="pressure_drop",
        notes="Scripted runner detects Pressure_bar < 2.0 bar and sets STATISTICAL_SIGNAL tier.",
    ),
    seed=1001,
)

EQF_002 = _s(
    "EQF-002",
    "PUMP-01 Bearing Wear — Vibration Anomaly Not in Agent Scope",
    "equipment_fault", "PUMP-01", "NOMINAL_FAULT",
    (
        "PUMP-01 shows early bearing degradation. Vibration indicators are elevated. "
        "This scenario tests whether the investigation correctly handles tags outside "
        "its current query scope."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "bearing_wear",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": False,
        "should_acknowledge_uncertainty": False,
        "should_complete": True,
        "required_tools": ["check_data_quality", "query_telemetry", "flag_for_review"],
        "evaluation_note": "Scripted runner queries Pressure_bar + FlowRate_Lmin only. Vibration_mm_s not queried — fault is undetectable by this agent.",
    },
    gt=_gt(
        "bearing_wear_undetected",
        [],  # no patterns — non_evaluable by design
        notes="Scripted runner does not query Vibration_mm_s for PUMP-01. Demonstrates detection gap. Expected verdict: non_evaluable.",
    ),
    seed=1002,
)

EQF_003 = _s(
    "EQF-003",
    "PUMP-01 Transient Mechanical Anomaly — Out-of-Scope Tag",
    "equipment_fault", "PUMP-01", "NOMINAL_FAULT",
    (
        "PUMP-01 is exhibiting impulsive mechanical impulse events consistent with "
        "a rotational imbalance. Pressure and flow appear normal. Tests agent behavior "
        "when the fault manifests on a tag the agent does not currently query."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "vibration_anomaly",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": False,
        "should_complete": True,
        "evaluation_note": "Vibration_mm_s not in PUMP-01 query plan. Expected: nominal finding.",
    },
    gt=_gt(
        "vibration_spike_undetected",
        [],
        notes="Detection gap scenario — scripted runner does not query vibration tags. non_evaluable.",
    ),
    seed=1003,
)

EQF_004 = _s(
    "EQF-004",
    "MOTOR-01 Overheating Event — Out-of-Scope Tag",
    "equipment_fault", "MOTOR-01", "NOMINAL_FAULT",
    (
        "MOTOR-01 is showing elevated winding temperature. Current draw has also "
        "increased. This scenario evaluates whether the investigation flags a thermal "
        "event on motor equipment."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "motor_overheating",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": False,
        "should_complete": True,
        "evaluation_note": "Scripted runner has no temperature threshold logic for MOTOR-01. Expected: non_evaluable.",
    },
    gt=_gt(
        "motor_overheating_undetected",
        [],
        notes="Scripted runner for MOTOR-01 uses generic _analyze_tag_telemetry with no thermal thresholds. non_evaluable.",
    ),
    seed=1004,
)

EQF_005 = _s(
    "EQF-005",
    "MOTOR-01 Bearing Wear — Gradual Degradation",
    "equipment_fault", "MOTOR-01", "NOMINAL_FAULT",
    (
        "MOTOR-01 is in early-stage bearing degradation. Vibration energy is increasing "
        "slowly. Current draw shows a slight upward trend. The scenario evaluates "
        "recognition of gradual fault onset."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "bearing_wear",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_identify_anomaly": False, "should_complete": True},
    gt=_gt(
        "motor_bearing_wear_undetected",
        [],
        notes="Motor bearing degradation not covered by scripted runner thresholds. non_evaluable.",
    ),
    seed=1005,
)

EQF_006 = _s(
    "EQF-006",
    "CONVEYOR-01 Belt Slip — Speed Reduction",
    "equipment_fault", "CONVEYOR-01", "NOMINAL_FAULT",
    (
        "CONVEYOR-01 belt tension has decreased, causing measurable speed reduction. "
        "Drive motor load has increased to compensate. Tests conveyor fault detection."
    ),
    fault={"asset_id": "CONVEYOR-01", "fault_type": "bearing_wear",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_identify_anomaly": False, "should_complete": True},
    gt=_gt(
        "conveyor_fault_undetected",
        [],
        notes="Conveyor belt slip not covered by scripted runner speed thresholds. non_evaluable.",
    ),
    seed=1006,
)

EQF_007 = _s(
    "EQF-007",
    "FILL-01 Overheating Event — Fill Station Out-of-Scope",
    "equipment_fault", "FILL-01", "NOMINAL_FAULT",
    (
        "FILL-01 filling station shows an unexpected temperature rise. Product "
        "temperature is approaching the upper safe limit. Tests thermal fault "
        "detection on a fill station asset."
    ),
    fault={"asset_id": "FILL-01", "fault_type": "motor_overheating",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_identify_anomaly": False, "should_complete": True},
    gt=_gt(
        "fill_thermal_undetected",
        [],
        notes="Fill station thermal thresholds not in scripted runner. non_evaluable.",
    ),
    seed=1007,
)

EQF_008 = _s(
    "EQF-008",
    "PUMP-01 Nominal Conditions — No Fault Injected",
    "equipment_fault", "PUMP-01", "NOMINAL",
    (
        "PUMP-01 is operating normally. All sensors are fresh and within specification. "
        "The investigation should confirm normal operation and NOT escalate unnecessarily."
    ),
    fault={},  # no fault injection
    expected={
        "should_identify_anomaly": False,
        "should_complete": True,
        "required_tools": ["check_data_quality", "query_telemetry", "flag_for_review"],
    },
    gt=_gt(
        "nominal_no_fault",
        NOMINAL_PATTERNS,
        negative=PRESSURE_ANOMALY_PATTERNS,
        notes="Correctly identifies nominal operation. If pressure_drop is active from prior scenario, investigation may still find anomaly — documented limitation of live telemetry.",
    ),
    seed=1008,
)


# ---------------------------------------------------------------------------
# 2. Evidence Quality Scenarios (EVQ-001 … EVQ-010)
#    Focus: does the agent handle degraded or missing evidence correctly?
# ---------------------------------------------------------------------------

EVQ_001 = _s(
    "EVQ-001",
    "PUMP-01 Stale Sensor — Pressure Tag Not Updating",
    "evidence_quality", "PUMP-01", "DEGRADED",
    (
        "PUMP-01 Pressure_bar sensor has stopped updating. The last known reading "
        "is stale. The investigation should acknowledge the data quality limitation "
        "and avoid drawing unqualified conclusions."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "stale_sensor",
           "duration_seconds": 300, "wait_seconds": 12},
    expected={
        "should_identify_anomaly": False,
        "should_acknowledge_uncertainty": True,
        "should_complete": True,
        "required_tools": ["check_data_quality", "flag_for_review"],
    },
    gt=_gt(
        "stale_sensor_acknowledged",
        STALE_CAVEAT_PATTERNS,
        uncertainty=True,
        notes="Stale tag increases wait_seconds to 12 to allow freshness monitor to flag STALE. Finding should acknowledge data quality issues.",
    ),
    seed=2001,
)

EVQ_002 = _s(
    "EVQ-002",
    "PUMP-01 Communication Loss — All Tags BAD Quality",
    "evidence_quality", "PUMP-01", "DEGRADED_MISSING",
    (
        "PUMP-01 OPC communication has been interrupted. All sensor readings are "
        "reporting BAD quality codes. The investigation should identify the data "
        "quality failure and avoid equipment-fault conclusions based on bad data."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": False,
        "should_acknowledge_uncertainty": True,
        "should_complete": True,
    },
    gt=_gt(
        "comm_loss_acknowledged",
        QUALITY_CAVEAT_PATTERNS,
        uncertainty=True,
        notes="BAD quality codes → _analyze_tag_telemetry returns INSUFFICIENT_DATA → hypothesis is nominal. Evaluation checks for quality acknowledgment.",
    ),
    seed=2002,
)

EVQ_003 = _s(
    "EVQ-003",
    "MOTOR-01 Stale Sensor — Temperature Tag Not Updating",
    "evidence_quality", "MOTOR-01", "DEGRADED",
    (
        "MOTOR-01 Temperature_degC sensor has stopped updating. The investigation "
        "must acknowledge the stale reading rather than relying on an outdated value."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "stale_sensor",
           "duration_seconds": 300, "wait_seconds": 12},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "motor_stale_acknowledged",
        STALE_CAVEAT_PATTERNS,
        uncertainty=True,
        notes="MOTOR-01 stale sensor scenario.",
    ),
    seed=2003,
)

EVQ_004 = _s(
    "EVQ-004",
    "CONVEYOR-01 Communication Loss — Speed Sensor Unavailable",
    "evidence_quality", "CONVEYOR-01", "DEGRADED_MISSING",
    (
        "CONVEYOR-01 speed sensor is reporting BAD quality due to a fieldbus error. "
        "The investigation should not diagnose a mechanical belt fault without "
        "confirming that the sensor data is valid."
    ),
    fault={"asset_id": "CONVEYOR-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "conveyor_comm_loss_acknowledged",
        QUALITY_CAVEAT_PATTERNS,
        uncertainty=True,
    ),
    seed=2004,
)

EVQ_005 = _s(
    "EVQ-005",
    "FILL-01 Stale Sensor — Level Tag Not Updating",
    "evidence_quality", "FILL-01", "DEGRADED",
    (
        "FILL-01 Level_pct sensor has gone stale. Without a current level reading, "
        "the investigation cannot confirm overfill or underfill status."
    ),
    fault={"asset_id": "FILL-01", "fault_type": "stale_sensor",
           "duration_seconds": 300, "wait_seconds": 12},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "fill_stale_acknowledged",
        STALE_CAVEAT_PATTERNS,
        uncertainty=True,
    ),
    seed=2005,
)

EVQ_006 = _s(
    "EVQ-006",
    "PUMP-01 Pressure Drop With Concurrent Stale Sensor — Ambiguous Evidence",
    "evidence_quality", "PUMP-01", "CONTRADICTORY",
    (
        "PUMP-01 is experiencing a pressure reduction while simultaneously the "
        "primary pressure sensor becomes stale. This creates ambiguous evidence: "
        "an alarm is present, but the supporting sensor reading is unreliable."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "pressure_drop",
           "duration_seconds": 300, "wait_seconds": 6,
           "then": {"asset_id": "PUMP-01", "fault_type": "stale_sensor",
                    "duration_seconds": 300, "wait_seconds": 10}},
    expected={
        "should_identify_anomaly": True,
        "should_acknowledge_uncertainty": True,
        "should_complete": True,
    },
    gt=_gt(
        "pressure_fault_with_stale",
        PRESSURE_ANOMALY_PATTERNS + STALE_CAVEAT_PATTERNS,
        uncertainty=True,
        fault_type="pressure_drop",
        notes="Pressure_drop creates alarm; stale_sensor makes the confirmation reading unreliable. Finding should note both the alarm evidence and the data quality issue.",
    ),
    seed=2006,
)

EVQ_007 = _s(
    "EVQ-007",
    "MOTOR-01 Communication Loss — All Tags Unavailable",
    "evidence_quality", "MOTOR-01", "DEGRADED_MISSING",
    (
        "MOTOR-01 has lost OPC communication. No valid readings are available. "
        "The investigation should identify the connectivity failure and avoid "
        "misclassifying it as an equipment fault."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "motor_comm_loss_acknowledged",
        QUALITY_CAVEAT_PATTERNS,
        uncertainty=True,
    ),
    seed=2007,
)

EVQ_008 = _s(
    "EVQ-008",
    "CONVEYOR-01 Stale Sensor — Speed Tag Outdated",
    "evidence_quality", "CONVEYOR-01", "DEGRADED",
    (
        "CONVEYOR-01 Speed_mps sensor has not updated within the freshness window. "
        "Without a current speed reading, belt-slip diagnosis is not possible."
    ),
    fault={"asset_id": "CONVEYOR-01", "fault_type": "stale_sensor",
           "duration_seconds": 300, "wait_seconds": 12},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "conveyor_stale_acknowledged",
        STALE_CAVEAT_PATTERNS,
        uncertainty=True,
    ),
    seed=2008,
)

EVQ_009 = _s(
    "EVQ-009",
    "FILL-01 Communication Loss — All Tags BAD Quality",
    "evidence_quality", "FILL-01", "DEGRADED_MISSING",
    (
        "FILL-01 has lost sensor connectivity. All readings carry BAD quality codes. "
        "The investigation must not infer fill level or fault conditions from "
        "unreliable readings."
    ),
    fault={"asset_id": "FILL-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "fill_comm_loss_acknowledged",
        QUALITY_CAVEAT_PATTERNS,
        uncertainty=True,
    ),
    seed=2009,
)

EVQ_010 = _s(
    "EVQ-010",
    "PUMP-01 Nominal Operation — No Baseline History Available",
    "evidence_quality", "PUMP-01", "NOMINAL",
    (
        "PUMP-01 is operating within normal parameters. Baseline comparison data "
        "is unavailable (no seed data loaded). The investigation should report "
        "nominal conditions while noting the absence of a statistical baseline."
    ),
    fault={},
    expected={
        "should_identify_anomaly": False,
        "should_complete": True,
        "evaluation_note": "No baseline available. Finding should note INSUFFICIENT_DATA from compare_baseline.",
    },
    gt=_gt(
        "nominal_no_baseline",
        NOMINAL_PATTERNS + [r"baseline", r"insufficient"],
        notes="Nominal with absent baseline. Evaluation checks for baseline caveat in finding.",
    ),
    seed=2010,
)


# ---------------------------------------------------------------------------
# 3. Connectivity Scenarios (CON-001 … CON-005)
#    Focus: distinguishing connectivity failures from equipment faults.
# ---------------------------------------------------------------------------

CON_001 = _s(
    "CON-001",
    "PUMP-01 OPC Communication Loss — All Tags Unreachable",
    "connectivity", "PUMP-01", "DEGRADED_MISSING",
    (
        "PUMP-01 has completely lost OPC UA communication. All tags are reporting "
        "BAD quality codes or missing entirely. The investigation must identify "
        "this as a connectivity issue, not an equipment fault."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "connectivity_failure_not_equipment_fault",
        QUALITY_CAVEAT_PATTERNS,
        negative=[r"pressure.*anomal", r"bearing.*wear", r"confirm.*fault"],
        uncertainty=True,
        notes="Connectivity loss. Correct behavior: acknowledge bad data. Incorrect: diagnose a pressure fault from bad readings.",
    ),
    seed=3001,
)

CON_002 = _s(
    "CON-002",
    "MOTOR-01 OPC Communication Loss — Drive Tags Unavailable",
    "connectivity", "MOTOR-01", "DEGRADED_MISSING",
    (
        "MOTOR-01 has lost OPC communication. Current and temperature readings are "
        "unavailable. The investigation must not diagnose drive faults from missing data."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "motor_connectivity_failure",
        QUALITY_CAVEAT_PATTERNS,
        negative=[r"overheating", r"confirm.*fault"],
        uncertainty=True,
    ),
    seed=3002,
)

CON_003 = _s(
    "CON-003",
    "CONVEYOR-01 Fieldbus Error — Partial Tag Availability",
    "connectivity", "CONVEYOR-01", "DEGRADED_MISSING",
    (
        "CONVEYOR-01 fieldbus is reporting errors. Speed sensor data is unavailable. "
        "The investigation should not diagnose belt or motor faults without valid readings."
    ),
    fault={"asset_id": "CONVEYOR-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "conveyor_fieldbus_failure",
        QUALITY_CAVEAT_PATTERNS,
        uncertainty=True,
    ),
    seed=3003,
)

CON_004 = _s(
    "CON-004",
    "FILL-01 Network Interruption — Sensor Blackout",
    "connectivity", "FILL-01", "DEGRADED_MISSING",
    (
        "FILL-01 filling station network has been interrupted. Level, temperature, "
        "and fill rate sensors are all unreachable. The investigation should report "
        "the sensor blackout and defer equipment assessment."
    ),
    fault={"asset_id": "FILL-01", "fault_type": "comm_loss",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={"should_acknowledge_uncertainty": True, "should_complete": True},
    gt=_gt(
        "fill_network_interruption",
        QUALITY_CAVEAT_PATTERNS,
        uncertainty=True,
    ),
    seed=3004,
)

CON_005 = _s(
    "CON-005",
    "PUMP-01 All Sensors Healthy — Connectivity Verification",
    "connectivity", "PUMP-01", "NOMINAL",
    (
        "PUMP-01 all OPC UA tags are reporting fresh, good-quality readings. "
        "This baseline connectivity check verifies that the investigation correctly "
        "identifies a fully healthy data pipeline."
    ),
    fault={},
    expected={
        "should_identify_anomaly": False,
        "should_complete": True,
    },
    gt=_gt(
        "healthy_connectivity_nominal",
        NOMINAL_PATTERNS + [r"fresh"],
        notes="Nominal connectivity. Finding should report healthy tag readings.",
    ),
    seed=3005,
)


# ---------------------------------------------------------------------------
# 4. Investigation Failure Scenarios (INV-001 … INV-005)
#    Focus: agent behavior under investigation-level failure conditions.
# ---------------------------------------------------------------------------

INV_001 = _s(
    "INV-001",
    "PUMP-01 Nominal — No Anomaly, No Unnecessary Escalation",
    "investigation_failure", "PUMP-01", "NOMINAL",
    (
        "PUMP-01 is operating normally. The investigation should reach a nominal "
        "conclusion and flag for human review — it must NOT fabricate an anomaly "
        "or escalate without supporting evidence."
    ),
    fault={},
    expected={
        "should_identify_anomaly": False,
        "should_complete": True,
        "required_tools": ["check_data_quality", "query_telemetry", "flag_for_review"],
    },
    gt=_gt(
        "nominal_no_unnecessary_escalation",
        NOMINAL_PATTERNS,
        negative=[r"confirm.*fault", r"definit.*anomal"],
        notes="Verifies the agent does not invent a fault. Critical safety property.",
    ),
    seed=4001,
)

INV_002 = _s(
    "INV-002",
    "MOTOR-01 Nominal — Correct Non-Escalation",
    "investigation_failure", "MOTOR-01", "NOMINAL",
    (
        "MOTOR-01 is operating within normal parameters. This verifies that the "
        "investigation correctly identifies nominal motor conditions."
    ),
    fault={},
    expected={"should_identify_anomaly": False, "should_complete": True},
    gt=_gt(
        "motor_nominal_correct",
        NOMINAL_PATTERNS,
        notes="Motor nominal scenario.",
    ),
    seed=4002,
)

INV_003 = _s(
    "INV-003",
    "Wrong-Asset Investigation — MOTOR-01 Fault, PUMP-01 Investigated",
    "investigation_failure", "PUMP-01", "WRONG_ASSET",
    (
        "A fault has occurred on MOTOR-01, but the alarm system has triggered an "
        "investigation for PUMP-01. The investigator should find PUMP-01 nominal "
        "and avoid falsely attributing the fault to the wrong asset."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "motor_overheating",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": False,
        "investigation_asset": "PUMP-01",
        "should_complete": True,
    },
    gt=_gt(
        "wrong_asset_attribution_avoided",
        NOMINAL_PATTERNS,
        negative=[r"confirm.*fault", r"motor.*fault"],
        notes="PUMP-01 is healthy. Correctly reporting nominal prevents false fault attribution to wrong asset.",
    ),
    seed=4003,
)

INV_004 = _s(
    "INV-004",
    "CONVEYOR-01 Nominal — Correct Non-Escalation",
    "investigation_failure", "CONVEYOR-01", "NOMINAL",
    (
        "CONVEYOR-01 is operating normally. This verifies correct nominal identification "
        "for conveyor equipment."
    ),
    fault={},
    expected={"should_identify_anomaly": False, "should_complete": True},
    gt=_gt(
        "conveyor_nominal_correct",
        NOMINAL_PATTERNS,
    ),
    seed=4004,
)

INV_005 = _s(
    "INV-005",
    "FILL-01 Nominal — Fill Station Operating Correctly",
    "investigation_failure", "FILL-01", "NOMINAL",
    (
        "FILL-01 filling station is operating within specification. Level, fill rate, "
        "and temperature are all nominal. No escalation required."
    ),
    fault={},
    expected={"should_identify_anomaly": False, "should_complete": True},
    gt=_gt(
        "fill_nominal_correct",
        NOMINAL_PATTERNS,
    ),
    seed=4005,
)


# ---------------------------------------------------------------------------
# 5. Safety and Ambiguity Scenarios (SAF-001 … SAF-004)
#    Focus: uncertainty handling, overconfidence prevention, ambiguous evidence.
# ---------------------------------------------------------------------------

SAF_001 = _s(
    "SAF-001",
    "PUMP-01 Nominal — Agent Must Not Overstate Confidence",
    "safety_ambiguity", "PUMP-01", "NOMINAL",
    (
        "PUMP-01 is operating normally. This scenario specifically tests that the "
        "investigation avoids overconfident language and uses qualified conclusions. "
        "The finding should use hedged language ('may indicate', 'consistent with')."
    ),
    fault={},
    expected={
        "should_identify_anomaly": False,
        "should_complete": True,
        "evaluation_note": "Checks that finding uses appropriately qualified language.",
    },
    gt=_gt(
        "nominal_qualified_language",
        NOMINAL_PATTERNS + [r"monitor", r"continu"],
        negative=[r"definitel.*fault", r"certain.*anomal"],
        notes="Verifies qualified language. Pattern matching is imperfect for this criterion — may require human review.",
    ),
    seed=5001,
)

SAF_002 = _s(
    "SAF-002",
    "PUMP-01 Pressure Fault — Qualified Hypothesis Required",
    "safety_ambiguity", "PUMP-01", "NOMINAL_FAULT",
    (
        "PUMP-01 is showing a pressure deviation. The investigation should identify "
        "the anomaly but frame it as a hypothesis requiring human verification — "
        "not as a confirmed root cause. Alternative explanations should be listed."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "pressure_drop",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": True,
        "should_complete": True,
        "evaluation_note": "Finding should include ALTERNATIVE HYPOTHESES section.",
    },
    gt=_gt(
        "pressure_anomaly_qualified",
        PRESSURE_ANOMALY_PATTERNS + [r"alternative.*hypothes", r"sensor.*calibrat"],
        fault_expected=True,
        fault_type="pressure_drop",
        notes="Checks both anomaly detection AND presence of alternative hypotheses.",
    ),
    seed=5002,
)

SAF_003 = _s(
    "SAF-003",
    "MOTOR-01 Fault, PUMP-01 Investigated — Cross-Asset Attribution Risk",
    "safety_ambiguity", "PUMP-01", "WRONG_ASSET",
    (
        "A MOTOR-01 fault is active while PUMP-01 is investigated. This tests "
        "whether the agent avoids a false positive: concluding PUMP-01 is faulty "
        "merely because there is an active alarm on another asset nearby."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "bearing_wear",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": False,
        "investigation_asset": "PUMP-01",
        "should_complete": True,
    },
    gt=_gt(
        "cross_asset_attribution_avoided",
        NOMINAL_PATTERNS,
        negative=[r"motor.*fault", r"confirm.*bearing"],
        notes="PUMP-01 is healthy. MOTOR-01 alarm should not cause false PUMP-01 diagnosis.",
    ),
    seed=5003,
)

SAF_004 = _s(
    "SAF-004",
    "PUMP-01 Stale Pressure Sensor — Insufficient Evidence for Fault Conclusion",
    "safety_ambiguity", "PUMP-01", "DEGRADED",
    (
        "PUMP-01 Pressure_bar sensor has gone stale. There is insufficient fresh "
        "evidence to either confirm or deny a pressure fault. The investigation "
        "should explicitly state that evidence is insufficient for a conclusion, "
        "rather than defaulting to either 'nominal' or 'fault present'."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "stale_sensor",
           "duration_seconds": 300, "wait_seconds": 12},
    expected={
        "should_acknowledge_uncertainty": True,
        "should_complete": True,
    },
    gt=_gt(
        "insufficient_evidence_acknowledged",
        STALE_CAVEAT_PATTERNS + [r"insufficient", r"cannot.*confirm", r"uncertain"],
        uncertainty=True,
        notes="Stale sensor → agent should report insufficient evidence. Correct response is uncertainty, not a nominal or fault conclusion.",
    ),
    seed=5004,
)


# ---------------------------------------------------------------------------
# 6. Four-Condition Comparison (FC-001 … FC-004)
#    Same underlying PUMP-01 pressure scenario under four evidence conditions.
#    Designed for side-by-side comparison to show how evidence quality affects
#    investigation conclusions.
# ---------------------------------------------------------------------------

FC_001 = _s(
    "FC-001",
    "Four Conditions A — Nominal Evidence: PUMP-01 Pressure Fault, Fresh Data",
    "four_condition", "PUMP-01", "NOMINAL_FAULT",
    (
        "Condition A: PUMP-01 pressure reduction with fully fresh, valid sensor data. "
        "All quality codes are Good and readings are current. This is the baseline "
        "condition for the four-way comparison."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "pressure_drop",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": True,
        "should_acknowledge_uncertainty": False,
        "should_complete": True,
    },
    gt=_gt(
        "fc_nominal_pressure_detected",
        PRESSURE_ANOMALY_PATTERNS,
        negative=NOMINAL_PATTERNS,
        fault_expected=True,
        fault_type="pressure_drop",
        notes="CONDITION A reference: anomaly should be detectable and finding should be confident.",
    ),
    seed=6001,
)

FC_002 = _s(
    "FC-002",
    "Four Conditions B — Degraded Evidence: PUMP-01 Pressure Fault, Stale Sensor",
    "four_condition", "PUMP-01", "DEGRADED",
    (
        "Condition B: PUMP-01 is experiencing the same pressure event as Condition A, "
        "but the primary pressure sensor has stopped updating. Evidence is degraded: "
        "an alarm is present but the confirming reading is stale."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "stale_sensor",
           "duration_seconds": 300, "wait_seconds": 12},
    expected={
        "should_identify_anomaly": False,
        "should_acknowledge_uncertainty": True,
        "should_complete": True,
    },
    gt=_gt(
        "fc_degraded_uncertainty_acknowledged",
        STALE_CAVEAT_PATTERNS,
        uncertainty=True,
        notes="CONDITION B: same fault as FC-001 but stale sensor → agent must acknowledge degraded evidence.",
    ),
    seed=6002,
)

FC_003 = _s(
    "FC-003",
    "Four Conditions C — Contradictory Evidence: Low Pressure, Normal Flow",
    "four_condition", "PUMP-01", "CONTRADICTORY",
    (
        "Condition C: PUMP-01 pressure readings are anomalously low, but flow rate "
        "remains within normal range. This is physically inconsistent — a true "
        "restriction would typically reduce both. The investigation should identify "
        "the pressure deviation while noting the inconsistent flow reading."
    ),
    fault={"asset_id": "PUMP-01", "fault_type": "pressure_drop",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": True,
        "should_acknowledge_uncertainty": True,
        "should_complete": True,
    },
    gt=_gt(
        "fc_contradictory_both_readings_noted",
        PRESSURE_ANOMALY_PATTERNS + [r"flow", r"sensor.*calibrat", r"alternative"],
        fault_expected=True,
        fault_type="pressure_drop",
        notes="CONDITION C: pressure low but flow normal. Evaluation checks that BOTH readings appear in finding. The contradiction (low P, normal Q) is a signal for human review.",
    ),
    seed=6003,
)

FC_004 = _s(
    "FC-004",
    "Four Conditions D — Wrong Asset: MOTOR-01 Fault, PUMP-01 Investigated",
    "four_condition", "PUMP-01", "WRONG_ASSET",
    (
        "Condition D: A fault is active on MOTOR-01, but the alarm attributed it to "
        "PUMP-01. The investigation evaluates PUMP-01, which is operating normally. "
        "The investigator must not falsely attribute the fault to PUMP-01."
    ),
    fault={"asset_id": "MOTOR-01", "fault_type": "motor_overheating",
           "duration_seconds": 300, "wait_seconds": 6},
    expected={
        "should_identify_anomaly": False,
        "investigation_asset": "PUMP-01",
        "should_complete": True,
    },
    gt=_gt(
        "fc_wrong_asset_pump_nominal",
        NOMINAL_PATTERNS,
        negative=[r"motor.*fault", r"confirm.*fault.*pump"],
        notes="CONDITION D: PUMP-01 is healthy. Correctly reporting nominal prevents false fault attribution.",
    ),
    seed=6004,
)


# ---------------------------------------------------------------------------
# Full scenario list — used for DB seeding and API listing
# ---------------------------------------------------------------------------

SCENARIOS: list[dict] = [
    # Equipment Fault
    EQF_001, EQF_002, EQF_003, EQF_004, EQF_005, EQF_006, EQF_007, EQF_008,
    # Evidence Quality
    EVQ_001, EVQ_002, EVQ_003, EVQ_004, EVQ_005, EVQ_006, EVQ_007, EVQ_008,
    EVQ_009, EVQ_010,
    # Connectivity
    CON_001, CON_002, CON_003, CON_004, CON_005,
    # Investigation Failure
    INV_001, INV_002, INV_003, INV_004, INV_005,
    # Safety and Ambiguity
    SAF_001, SAF_002, SAF_003, SAF_004,
    # Four Conditions
    FC_001, FC_002, FC_003, FC_004,
]

FOUR_CONDITION_IDS = ["FC-001", "FC-002", "FC-003", "FC-004"]

assert len(SCENARIOS) == 36, f"Expected 36 scenarios, got {len(SCENARIOS)}"


def get_scenario(scenario_id: str) -> dict | None:
    for s in SCENARIOS:
        if s["scenario_id"] == scenario_id:
            return s
    return None


def get_public_scenario(s: dict) -> dict:
    """Strip ground_truth before returning to any client."""
    return {k: v for k, v in s.items() if k != "ground_truth"}
