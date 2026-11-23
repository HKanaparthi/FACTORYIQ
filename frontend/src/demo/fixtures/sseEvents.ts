// DEMO FIXTURE — Illustrative SSE event sequence for scripted investigation replay.
// Constructed to match the expected output of app/agent/runner.py _scripted_core()
// for PUMP-01 with pressure_drop fault active. Tool calls and summaries are derived
// from scripted runner logic and synthetic telemetry values; not a live capture.
// Label: "Recorded Scripted Investigation — No live AI inference."
import type { SSEEvent } from '../../api/types'

export const DEMO_SSE_EVENTS: SSEEvent[] = [
  // Tool 1: get_recent_events
  { type: 'tool_call',   tool_name: 'get_recent_events',    inputs: { asset_id: 'PUMP-01', since_minutes: 120 }, sequence: 1 },
  { type: 'tool_result', tool_name: 'get_recent_events',    success: true, summary: '5 events found', sequence: 1 },
  // Tool 2: check_data_quality
  { type: 'tool_call',   tool_name: 'check_data_quality',   inputs: { asset_id: 'PUMP-01' }, sequence: 2 },
  { type: 'tool_result', tool_name: 'check_data_quality',   success: true, summary: '4/4 tags FRESH', sequence: 2 },
  // Tool 3: query_telemetry Pressure_bar
  { type: 'tool_call',   tool_name: 'query_telemetry',      inputs: { asset_id: 'PUMP-01', tag_name: 'Pressure_bar', start_iso: '2026-11-22T16:50:00Z', end_iso: '2026-11-22T16:55:00Z' }, sequence: 3 },
  { type: 'tool_result', tool_name: 'query_telemetry',      success: true, summary: '10 readings — latest 0.98bar', sequence: 3 },
  // Tool 4: query_telemetry FlowRate_Lmin
  { type: 'tool_call',   tool_name: 'query_telemetry',      inputs: { asset_id: 'PUMP-01', tag_name: 'FlowRate_Lmin', start_iso: '2026-11-22T16:50:00Z', end_iso: '2026-11-22T16:55:00Z' }, sequence: 4 },
  { type: 'tool_result', tool_name: 'query_telemetry',      success: true, summary: '10 readings — latest 55.20L/min', sequence: 4 },
  // Tool 5: compare_baseline
  { type: 'tool_call',   tool_name: 'compare_baseline',     inputs: { asset_id: 'PUMP-01', tag_name: 'Pressure_bar', window_minutes: 60 }, sequence: 5 },
  { type: 'tool_result', tool_name: 'compare_baseline',     success: true, summary: 'No baseline data — seed baseline to enable', sequence: 5 },
  // Tool 6: query_equipment_docs
  { type: 'tool_call',   tool_name: 'query_equipment_docs', inputs: { query_text: 'PUMP-01 Pressure_bar anomaly fault' }, sequence: 6 },
  { type: 'tool_result', tool_name: 'query_equipment_docs', success: true, summary: '2 relevant documents found', sequence: 6 },
  // Tool 7: flag_for_review
  { type: 'tool_call',   tool_name: 'flag_for_review',      inputs: { action: 'submit_finding' }, sequence: 7 },
  { type: 'tool_result', tool_name: 'flag_for_review',      success: true, summary: 'Finding submitted for human review', sequence: 7 },
  // Terminal events
  { type: 'complete', status: 'pending_review', tool_calls_used: 7 },
  { type: 'done' },
]

// Delay between each event (ms). Gives a natural "streaming" feel.
export const DEMO_SSE_DELAY_MS = 700
