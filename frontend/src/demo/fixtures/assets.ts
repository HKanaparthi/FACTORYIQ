// DEMO FIXTURE — Asset, alarm, and tag-health data.
// Source: simulator/tag_model.py nominal operating parameters.
// Scenario: PUMP-01 has an active pressure_drop fault (delta=-3.5 bar).
//           All other assets are nominal.
// Capture reference: 2026-11-22T16:40–17:00Z simulation window.
import type { AssetsResponse, AlarmResponse, TagHealthResponse } from '../../api/types'

export const DEMO_ASSETS: AssetsResponse = {
  assets: [
    {
      asset_id: 'PUMP-01',
      label: 'Centrifugal Pump',
      tags: ['Temperature_degC', 'Pressure_bar', 'Vibration_mm_s', 'FlowRate_Lmin'],
      health_status: 'WARNING',
      fresh_tags: 4,
      stale_tags: 0,
      missing_tags: 0,
      total_tags: 4,
      recent_alarms: 5,
      latest_investigation_id: 'b7e4c5f1-2d9a-4b8c-a7e6-f5d4c3b2a1e9',
      latest_investigation_status: 'pending_review',
    },
    {
      asset_id: 'MOTOR-01',
      label: 'Electric Motor',
      tags: ['Current_A', 'Temperature_degC', 'Speed_rpm'],
      health_status: 'HEALTHY',
      fresh_tags: 3,
      stale_tags: 0,
      missing_tags: 0,
      total_tags: 3,
      recent_alarms: 0,
      latest_investigation_id: 'c5f6d7e8-3e0b-4c9d-b8f7-e6e5d4c3b2a0',
      latest_investigation_status: 'approved',
    },
    {
      asset_id: 'CONVEYOR-01',
      label: 'Conveyor Belt',
      tags: ['Speed_mps', 'Temperature_degC'],
      health_status: 'HEALTHY',
      fresh_tags: 2,
      stale_tags: 0,
      missing_tags: 0,
      total_tags: 2,
      recent_alarms: 0,
      latest_investigation_id: 'd1e2f3a4-4f1c-4d0e-c9f8-f7e6d5c4b3a1',
      latest_investigation_status: 'approved',
    },
    {
      asset_id: 'FILL-01',
      label: 'Filling Station',
      tags: ['Level_pct', 'FillRate_Lmin', 'Temperature_degC'],
      health_status: 'HEALTHY',
      fresh_tags: 3,
      stale_tags: 0,
      missing_tags: 0,
      total_tags: 3,
      recent_alarms: 0,
      latest_investigation_id: null,
      latest_investigation_status: null,
    },
  ],
}

// Alarms from the last 60 minutes of the recording window.
// All alarms are for PUMP-01 triggered by the pressure_drop fault.
export const DEMO_ALARMS: AlarmResponse = {
  is_simulated: true,
  count: 5,
  alarms: [
    {
      alarm_id: 'd1e2f3a4-b5c6-7d8e-9f0a-1b2c3d4e5f6a',
      asset_id: 'PUMP-01',
      alarm_type: 'PRESSURE_LOW',
      severity: 'HIGH',
      message: 'PUMP-01 pressure dropped below threshold',
      triggered_at: '2026-11-22T16:41:15Z',
      acknowledged_at: null,
      raw_value: 1.02,
      threshold: 2.0,
    },
    {
      alarm_id: 'e2f3a4b5-c6d7-8e9f-0a1b-2c3d4e5f6a7b',
      asset_id: 'PUMP-01',
      alarm_type: 'PRESSURE_CRITICAL',
      severity: 'CRITICAL',
      message: 'PUMP-01 pressure dropped below threshold',
      triggered_at: '2026-11-22T16:42:30Z',
      acknowledged_at: null,
      raw_value: 0.98,
      threshold: 1.5,
    },
    {
      alarm_id: 'f3a4b5c6-d7e8-9f0a-1b2c-3d4e5f6a7b8c',
      asset_id: 'PUMP-01',
      alarm_type: 'FLOW_LOW',
      severity: 'HIGH',
      message: 'PUMP-01 flow rate below minimum threshold',
      triggered_at: '2026-11-22T16:43:00Z',
      acknowledged_at: null,
      raw_value: 54.8,
      threshold: 80.0,
    },
    {
      alarm_id: 'a4b5c6d7-e8f9-0a1b-2c3d-4e5f6a7b8c9d',
      asset_id: 'PUMP-01',
      alarm_type: 'PRESSURE_LOW',
      severity: 'HIGH',
      message: 'PUMP-01 pressure dropped below threshold',
      triggered_at: '2026-11-22T16:46:45Z',
      acknowledged_at: null,
      raw_value: 0.99,
      threshold: 2.0,
    },
    {
      alarm_id: 'b5c6d7e8-f9a0-1b2c-3d4e-5f6a7b8c9d0e',
      asset_id: 'PUMP-01',
      alarm_type: 'FLOW_LOW',
      severity: 'MEDIUM',
      message: 'PUMP-01 flow rate below minimum threshold',
      triggered_at: '2026-11-22T16:51:00Z',
      acknowledged_at: null,
      raw_value: 55.3,
      threshold: 80.0,
    },
  ],
}

export const DEMO_TAG_HEALTH: Record<string, TagHealthResponse> = {
  'PUMP-01': {
    is_simulated: true,
    tags: [
      {
        asset_id: 'PUMP-01',
        tag_name: 'Temperature_degC',
        last_update: '2026-11-22T16:59:50Z',
        freshness_status: 'FRESH',
        staleness_threshold_seconds: 10,
        updated_at: '2026-11-22T16:59:50Z',
      },
      {
        asset_id: 'PUMP-01',
        tag_name: 'Pressure_bar',
        last_update: '2026-11-22T16:59:52Z',
        freshness_status: 'FRESH',
        staleness_threshold_seconds: 10,
        updated_at: '2026-11-22T16:59:52Z',
      },
      {
        asset_id: 'PUMP-01',
        tag_name: 'Vibration_mm_s',
        last_update: '2026-11-22T16:59:51Z',
        freshness_status: 'FRESH',
        staleness_threshold_seconds: 10,
        updated_at: '2026-11-22T16:59:51Z',
      },
      {
        asset_id: 'PUMP-01',
        tag_name: 'FlowRate_Lmin',
        last_update: '2026-11-22T16:59:53Z',
        freshness_status: 'FRESH',
        staleness_threshold_seconds: 10,
        updated_at: '2026-11-22T16:59:53Z',
      },
    ],
  },
  'MOTOR-01': {
    is_simulated: true,
    tags: [
      { asset_id: 'MOTOR-01', tag_name: 'Current_A',       last_update: '2026-11-22T16:59:51Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:51Z' },
      { asset_id: 'MOTOR-01', tag_name: 'Temperature_degC',last_update: '2026-11-22T16:59:52Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:52Z' },
      { asset_id: 'MOTOR-01', tag_name: 'Speed_rpm',       last_update: '2026-11-22T16:59:50Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:50Z' },
    ],
  },
  'CONVEYOR-01': {
    is_simulated: true,
    tags: [
      { asset_id: 'CONVEYOR-01', tag_name: 'Speed_mps',       last_update: '2026-11-22T16:59:52Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:52Z' },
      { asset_id: 'CONVEYOR-01', tag_name: 'Temperature_degC',last_update: '2026-11-22T16:59:50Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:50Z' },
    ],
  },
  'FILL-01': {
    is_simulated: true,
    tags: [
      { asset_id: 'FILL-01', tag_name: 'Level_pct',       last_update: '2026-11-22T16:59:51Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:51Z' },
      { asset_id: 'FILL-01', tag_name: 'FillRate_Lmin',   last_update: '2026-11-22T16:59:52Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:52Z' },
      { asset_id: 'FILL-01', tag_name: 'Temperature_degC',last_update: '2026-11-22T16:59:50Z', freshness_status: 'FRESH', staleness_threshold_seconds: 10, updated_at: '2026-11-22T16:59:50Z' },
    ],
  },
}

export function getDemoTagHealth(assetId: string): TagHealthResponse {
  return DEMO_TAG_HEALTH[assetId] ?? { is_simulated: true, tags: [] }
}

export function getDemoAlarms(assetId?: string, sinceMinutes = 60): AlarmResponse {
  const cutoff = new Date('2026-11-22T17:00:00Z').getTime() - sinceMinutes * 60 * 1000
  const alarms = DEMO_ALARMS.alarms.filter(a => {
    const inTime = new Date(a.triggered_at).getTime() >= cutoff
    return assetId ? a.asset_id === assetId && inTime : inTime
  })
  return { is_simulated: true, count: alarms.length, alarms }
}
