// DEMO FIXTURE — Time-series telemetry readings.
// Source: simulator/tag_model.py physics (nominal values + pressure_drop fault profile).
// Window: 2026-11-22T16:00:00Z – 2026-11-22T16:57:00Z (20 readings × 3-min step).
// PUMP-01 pressure_drop fault active from T+40min (reading index 13 onward):
//   Pressure_bar shifts by -3.5 bar (nominal 4.5 → ~1.0 bar)
//   FlowRate_Lmin shifts by -65 L/min (nominal 120 → ~55 L/min)
// All other assets remain at nominal operating values throughout.
import type { TelemetryResponse, TelemetryReading } from '../../api/types'

const BASE = new Date('2026-11-22T16:00:00Z').getTime()
const STEP_MS = 3 * 60 * 1000 // 3 minutes
const TOTAL = 20

function ts(i: number): string {
  return new Date(BASE + i * STEP_MS).toISOString().replace('.000', '')
}

function goodReading(value: number, unit: string, source = 'SIMULATOR'): Omit<TelemetryReading, 'timestamp'> {
  return { value, opc_quality_code: 0, opc_quality_label: 'Good', unit, source }
}

// Pre-computed values per tag (20 readings each)
const PUMP01_PRESSURE_BAR = [
  4.48, 4.52, 4.49, 4.51, 4.47, 4.53, 4.50, 4.49, 4.52, 4.48,
  4.50, 4.47, 4.51, 1.02, 0.98, 1.01, 0.99, 1.03, 1.00, 0.97,
]
const PUMP01_FLOW_LMIN = [
  120.1, 119.8, 120.3, 119.7, 120.2, 119.9, 120.0, 120.4, 119.6, 120.1,
  119.8, 120.3, 119.7, 55.4, 54.8, 55.1, 55.7, 54.9, 55.3, 55.0,
]
const PUMP01_TEMP_DEG = [
  65.1, 64.8, 65.3, 64.9, 65.2, 65.0, 64.7, 65.4, 65.1, 64.8,
  65.2, 65.0, 65.3, 64.9, 65.1, 64.8, 65.0, 65.3, 65.1, 64.9,
]
const PUMP01_VIB_MMS = [
  2.08, 2.15, 2.09, 2.13, 2.10, 2.07, 2.14, 2.11, 2.09, 2.12,
  2.08, 2.15, 2.10, 2.13, 2.09, 2.11, 2.08, 2.14, 2.10, 2.12,
]
const MOTOR01_CURRENT_A = [
  12.48, 12.53, 12.47, 12.52, 12.49, 12.51, 12.46, 12.54, 12.50, 12.48,
  12.53, 12.47, 12.51, 12.49, 12.52, 12.48, 12.50, 12.47, 12.53, 12.51,
]
const MOTOR01_TEMP_DEG = [
  70.2, 69.8, 70.4, 69.9, 70.1, 70.3, 69.7, 70.2, 70.0, 70.5,
  69.8, 70.3, 70.1, 69.9, 70.4, 70.0, 70.2, 69.8, 70.3, 70.1,
]
const MOTOR01_SPEED_RPM = [
  1448, 1452, 1449, 1451, 1448, 1453, 1450, 1449, 1452, 1448,
  1451, 1450, 1448, 1452, 1449, 1451, 1448, 1453, 1450, 1449,
]
const CONVEYOR01_SPEED_MPS = [
  1.19, 1.21, 1.20, 1.18, 1.22, 1.20, 1.19, 1.21, 1.20, 1.18,
  1.22, 1.21, 1.20, 1.19, 1.21, 1.20, 1.18, 1.22, 1.21, 1.20,
]
const CONVEYOR01_TEMP_DEG = [
  42.1, 41.8, 42.3, 42.0, 41.9, 42.2, 42.0, 41.7, 42.3, 42.1,
  41.9, 42.2, 42.0, 41.8, 42.3, 42.1, 41.9, 42.2, 42.0, 42.1,
]
const FILL01_LEVEL_PCT = [
  68.1, 67.8, 68.3, 68.0, 67.9, 68.2, 68.0, 67.7, 68.3, 68.1,
  67.9, 68.2, 68.0, 67.8, 68.3, 68.1, 67.9, 68.2, 68.0, 68.1,
]
const FILL01_FILLRATE_LMIN = [
  85.1, 84.8, 85.3, 85.0, 84.9, 85.2, 85.0, 84.7, 85.3, 85.1,
  84.9, 85.2, 85.0, 84.8, 85.3, 85.1, 84.9, 85.2, 85.0, 85.1,
]
const FILL01_TEMP_DEG = [
  22.1, 21.9, 22.2, 22.0, 21.8, 22.1, 22.0, 21.9, 22.2, 22.1,
  21.8, 22.0, 22.1, 21.9, 22.2, 22.1, 21.8, 22.0, 22.1, 21.9,
]

function buildReadings(values: number[], unit: string): TelemetryReading[] {
  return values.map((v, i) => ({ timestamp: ts(i), ...goodReading(v, unit) }))
}

const ALL_READINGS: Record<string, Record<string, TelemetryReading[]>> = {
  'PUMP-01': {
    'Pressure_bar':     buildReadings(PUMP01_PRESSURE_BAR, 'bar'),
    'FlowRate_Lmin':    buildReadings(PUMP01_FLOW_LMIN, 'L/min'),
    'Temperature_degC': buildReadings(PUMP01_TEMP_DEG, 'degC'),
    'Vibration_mm_s':   buildReadings(PUMP01_VIB_MMS, 'mm/s'),
  },
  'MOTOR-01': {
    'Current_A':        buildReadings(MOTOR01_CURRENT_A, 'A'),
    'Temperature_degC': buildReadings(MOTOR01_TEMP_DEG, 'degC'),
    'Speed_rpm':        buildReadings(MOTOR01_SPEED_RPM, 'rpm'),
  },
  'CONVEYOR-01': {
    'Speed_mps':        buildReadings(CONVEYOR01_SPEED_MPS, 'm/s'),
    'Temperature_degC': buildReadings(CONVEYOR01_TEMP_DEG, 'degC'),
  },
  'FILL-01': {
    'Level_pct':        buildReadings(FILL01_LEVEL_PCT, '%'),
    'FillRate_Lmin':    buildReadings(FILL01_FILLRATE_LMIN, 'L/min'),
    'Temperature_degC': buildReadings(FILL01_TEMP_DEG, 'degC'),
  },
}

// Demo "now" = end of the recording window
export const DEMO_NOW = new Date('2026-11-22T17:00:00Z')

// playbackIndex: 0-19; returns readings up to that index (inclusive)
export function getDemoTelemetry(
  assetId: string,
  tagName: string,
  minutes: number,
  playbackIndex: number = TOTAL - 1,
): TelemetryResponse {
  const tagReadings = ALL_READINGS[assetId]?.[tagName] ?? []

  // Filter by time range (minutes from DEMO_NOW) and playback cursor
  const cutoffMs = DEMO_NOW.getTime() - minutes * 60 * 1000
  const playbackCutoffMs = BASE + playbackIndex * STEP_MS

  const unit = tagReadings[0]?.unit ?? ''
  const readings = tagReadings.filter((r, _i) => {
    const t = new Date(r.timestamp).getTime()
    return t >= cutoffMs && t <= playbackCutoffMs
  })

  return {
    asset_id: assetId,
    tag_name: tagName,
    minutes,
    is_simulated: true,
    count: readings.length,
    readings,
  }
}

export { TOTAL as DEMO_PLAYBACK_MAX_INDEX }
