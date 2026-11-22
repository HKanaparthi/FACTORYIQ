"""
Illustrative equipment documentation corpus for FactoryIQ.

All documents are internally authored for demonstration purposes and are
clearly labeled as illustrative. They are NOT sourced from real equipment
manuals or vendor documentation.

query_equipment_docs uses keyword scoring for retrieval (Milestone 2).
Milestone 6 will replace this with pgvector cosine similarity.
"""

from __future__ import annotations

CORPUS: list[dict] = [
    {
        "asset_type": "PUMP",
        "doc_type": "MAINTENANCE_GUIDE",
        "title": "Centrifugal Pump Bearing Maintenance Guide",
        "content": (
            "Bearing failure is the most common cause of centrifugal pump failure. "
            "Early-stage bearing wear produces elevated vibration in the 2–8 mm/s range accompanied by "
            "a gradual temperature rise of 10–25°C above baseline. The vibration signature precedes "
            "the temperature rise by 20–40 minutes in a typical radial bearing degradation sequence. "
            "Vibration readings above 8.5 mm/s require immediate investigation. "
            "Critical bearing failure is indicated by vibration exceeding 15 mm/s or temperature "
            "exceeding 110°C. Lubrication intervals must be maintained per OEM schedule; "
            "dry-running even briefly (under 60 seconds) can initiate bearing wear. "
            "Recommended actions: (1) Isolate pump from service if vibration > 12 mm/s. "
            "(2) Check lubrication levels and grease condition. "
            "(3) Schedule bearing inspection within 24 hours if vibration 8.5–12 mm/s."
        ),
        "keywords": [
            "bearing", "vibration", "temperature", "wear", "pump", "lubrication",
            "failure", "centrifugal", "radial", "degradation", "mm/s", "overheating",
        ],
        "source_ref": "FactoryIQ Illustrative Doc — Centrifugal Pump Bearing Maintenance Guide v1.0",
    },
    {
        "asset_type": "PUMP",
        "doc_type": "FAULT_REFERENCE",
        "title": "Pump Pressure and Flow Fault Reference",
        "content": (
            "An abrupt pressure drop (> 1 bar within 10 seconds) indicates one of three conditions: "
            "(1) blockage in the suction line, (2) valve failure (open or stuck), or "
            "(3) cavitation due to insufficient NPSH. "
            "A simultaneous drop in flow rate proportional to the pressure drop (> 50 L/min) "
            "is consistent with valve failure or blockage. "
            "If pressure drops but flow rate remains stable, check for a pressure sensor fault. "
            "Nominal operating pressure for this pump is 4.0–5.0 bar. "
            "Pressures below 1.0 bar indicate severe blockage or valve failure requiring immediate shutdown. "
            "Cavitation produces an erratic pressure signal oscillating ±0.5 bar at 2–5 Hz."
        ),
        "keywords": [
            "pressure", "flow", "pump", "blockage", "valve", "cavitation", "drop",
            "suction", "NPSH", "bar", "sensor", "shutdown", "flowrate",
        ],
        "source_ref": "FactoryIQ Illustrative Doc — Pump Pressure and Flow Fault Reference v1.0",
    },
    {
        "asset_type": "MOTOR",
        "doc_type": "FAULT_REFERENCE",
        "title": "Motor Electrical Fault and Overheating Reference",
        "content": (
            "Motor overheating is caused by overloading, inadequate cooling, or electrical faults. "
            "Current draw exceeding 20A with normal load indicates an electrical fault (winding insulation "
            "breakdown, rotor eccentricity, or voltage imbalance). "
            "Temperature rise above 100°C with concurrent current increase suggests rotor fault. "
            "Temperature rise without current increase suggests cooling failure (fan blocked, ambient temperature). "
            "Normal operating current is 10–15A at rated load. "
            "Derating: for each 10°C above nominal winding temperature, insulation life halves. "
            "Immediate shutdown recommended if winding temperature exceeds 130°C. "
            "Speed deviation > 50 rpm from 1450 rpm setpoint indicates load variation or slip increase."
        ),
        "keywords": [
            "motor", "overheating", "current", "temperature", "electrical", "winding",
            "cooling", "overload", "rotor", "insulation", "speed", "rpm", "voltage",
        ],
        "source_ref": "FactoryIQ Illustrative Doc — Motor Electrical Fault and Overheating Reference v1.0",
    },
    {
        "asset_type": "CONVEYOR",
        "doc_type": "MAINTENANCE_GUIDE",
        "title": "Conveyor Belt Speed Control and Fault Guide",
        "content": (
            "Normal conveyor speed is 1.0–1.5 m/s. Speed deviations greater than ±0.3 m/s from setpoint "
            "indicate belt tension issues, drive motor faults, or encoder failure. "
            "High-amplitude speed oscillation (noise > ±0.2 m/s at > 1 Hz) with no DC drift "
            "suggests encoder noise or drive controller instability rather than a mechanical fault. "
            "Gradual speed increase above 2.0 m/s with stable temperature indicates overdriving. "
            "Temperature above 75°C at the drive end indicates bearing friction or belt misalignment. "
            "Emergency stop activates if speed exceeds 2.8 m/s. "
            "Belt tracking should be inspected if temperature deviates > 15°C from baseline."
        ),
        "keywords": [
            "conveyor", "speed", "belt", "tension", "encoder", "drive", "motor",
            "oscillation", "tracking", "alignment", "temperature", "m/s", "noise",
        ],
        "source_ref": "FactoryIQ Illustrative Doc — Conveyor Belt Speed Control and Fault Guide v1.0",
    },
    {
        "asset_type": "FILL",
        "doc_type": "MAINTENANCE_GUIDE",
        "title": "Fill Station Level and Communication Fault Guide",
        "content": (
            "Fill station level control maintains 60–75% nominal level. "
            "Level above 90% triggers high-level alarm; above 95% activates automatic shutoff. "
            "Fill rate deviation > 20 L/min from 85 L/min setpoint requires investigation. "
            "Communication loss (Bad quality code on all FILL-01 tags simultaneously) indicates "
            "a network or fieldbus failure, not an equipment fault. "
            "Do not diagnose equipment failure based solely on Bad quality readings — "
            "restore communication first and re-evaluate sensor data. "
            "A single Bad-quality tag with others Good indicates sensor failure rather than communication loss. "
            "Temperature deviation > 5°C on FILL-01 may indicate fluid source temperature variation."
        ),
        "keywords": [
            "fill", "level", "communication", "bad quality", "fieldbus", "network",
            "flow", "rate", "alarm", "shutoff", "sensor", "temperature", "FILL-01",
        ],
        "source_ref": "FactoryIQ Illustrative Doc — Fill Station Level and Communication Fault Guide v1.0",
    },
    {
        "asset_type": "GENERAL",
        "doc_type": "ANALYSIS_GUIDE",
        "title": "Vibration Analysis and Bearing Failure Progression Guide",
        "content": (
            "Bearing failure progresses through four stages identifiable by vibration signature. "
            "Stage 1 (early wear): sub-synchronous vibration at 0.3–0.5× running speed; overall < 3 mm/s. "
            "Stage 2 (developing wear): natural frequency excitation; overall 3–8 mm/s, temperature +5°C. "
            "Stage 3 (advanced wear): synchronous sidebands; overall > 8 mm/s, temperature +15°C. "
            "Stage 4 (imminent failure): broadband noise floor rise; overall > 15 mm/s, temperature > nominal +25°C. "
            "Key diagnostic rule: vibration-first patterns (vibration rises before temperature) "
            "are characteristic of mechanical wear. Temperature-first patterns suggest "
            "lubrication or cooling faults. "
            "Data quality note: readings with Bad or Uncertain OPC UA quality codes must not be used "
            "as evidence for bearing wear diagnosis — restore good-quality readings first."
        ),
        "keywords": [
            "vibration", "bearing", "failure", "analysis", "stage", "wear",
            "temperature", "synchronous", "noise", "mechanical", "lubrication",
            "quality", "diagnostic", "mm/s", "progression",
        ],
        "source_ref": "FactoryIQ Illustrative Doc — Vibration Analysis and Bearing Failure Progression Guide v1.0",
    },
]


def search_docs(query_text: str, asset_type: str | None = None, top_k: int = 3) -> list[dict]:
    """Keyword-based document retrieval. Returns scored docs, highest score first."""
    query_tokens = set(query_text.lower().split())
    scored = []
    for doc in CORPUS:
        if asset_type and doc["asset_type"].upper() != asset_type.upper():
            continue
        kw_tokens = {k.lower() for k in doc["keywords"]}
        # Score = intersection count + partial content match bonus
        kw_score = len(query_tokens & kw_tokens)
        content_score = sum(1 for t in query_tokens if t in doc["content"].lower())
        score = kw_score * 2 + content_score
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:top_k]]
