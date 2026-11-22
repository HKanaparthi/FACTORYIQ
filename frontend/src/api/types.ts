export interface TagHealth {
  asset_id: string
  tag_name: string
  last_update: string | null
  freshness_status: 'FRESH' | 'STALE' | 'MISSING'
  staleness_threshold_seconds: number
  updated_at: string
}

export interface TagHealthResponse {
  is_simulated: boolean
  tags: TagHealth[]
}

export interface TelemetryReading {
  timestamp: string
  value: number
  opc_quality_code: number
  opc_quality_label: 'Good' | 'Bad' | 'Uncertain'
  unit: string
  source: string
}

export interface TelemetryResponse {
  asset_id: string
  tag_name: string
  minutes: number
  is_simulated: boolean
  count: number
  readings: TelemetryReading[]
}

export interface Alarm {
  alarm_id: string
  asset_id: string
  alarm_type: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  message: string
  triggered_at: string
  acknowledged_at: string | null
  raw_value: number | null
  threshold: number | null
}

export interface AlarmResponse {
  is_simulated: boolean
  count: number
  alarms: Alarm[]
}

export interface AssetSummary {
  asset_id: string
  label: string
  tags: string[]
  health_status: 'HEALTHY' | 'WARNING' | 'DEGRADED' | 'UNKNOWN'
  fresh_tags: number
  stale_tags: number
  missing_tags: number
  total_tags: number
  recent_alarms: number
  latest_investigation_id: string | null
  latest_investigation_status: string | null
}

export interface AssetsResponse {
  assets: AssetSummary[]
}

export type InvestigationStatus =
  | 'in_progress'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'failed'

export interface InvestigationSummary {
  investigation_id: string
  asset_id: string
  status: InvestigationStatus
  started_at: string
  completed_at: string | null
  has_finding: boolean
}

export interface EvidenceItem {
  evidence_id: string
  sequence_num: number
  tool_name: string
  tool_inputs: Record<string, unknown> | null
  tool_output: Record<string, unknown> | null
  evidence_tier: EvidenceTier
  recorded_at: string
  citation_text: string | null
}

export type EvidenceTier =
  | 'CONFIRMED_OBSERVATION'
  | 'STATISTICAL_SIGNAL'
  | 'CORROBORATING_EVIDENCE'
  | 'WEAK_SIGNAL'
  | 'INSUFFICIENT_DATA'

export interface Investigation {
  investigation_id: string
  asset_id: string
  trigger_alarm_id: string | null
  status: InvestigationStatus
  finding_text: string | null
  evidence_summary: string[] | null    // list of EvidenceTier strings from flag_for_review
  alt_hypotheses: string[] | null      // list of alternative hypothesis strings
  started_at: string
  completed_at: string | null
  is_simulated: boolean
  agent_model: string | null
  agent_error: string | null
  agent_tool_calls: number | null
  evidence_items: EvidenceItem[]
}

// ---------------------------------------------------------------------------
// Evaluation harness (Milestone 5)
// ---------------------------------------------------------------------------

export type EvalCategory =
  | 'equipment_fault'
  | 'evidence_quality'
  | 'connectivity'
  | 'investigation_failure'
  | 'safety_ambiguity'
  | 'four_condition'

export type EvidenceCondition =
  | 'NOMINAL'
  | 'NOMINAL_FAULT'
  | 'DEGRADED'
  | 'DEGRADED_MISSING'
  | 'CONTRADICTORY'
  | 'WRONG_ASSET'

export interface EvalScenario {
  scenario_id: string
  version: string
  name: string
  category: EvalCategory
  asset_id: string
  evidence_condition: EvidenceCondition
  description: string
  fault_config: Record<string, unknown>
  expected_behavior: Record<string, unknown>
  seed: number
  created_at?: string
}

export type DiagnosticVerdict =
  | 'correct'
  | 'incorrect'
  | 'acceptable_alt'
  | 'uncertain_correct'
  | 'non_evaluable'

export type EvalRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface EvalRunSummary {
  correct: number
  incorrect: number
  acceptable_alt: number
  uncertain_correct: number
  non_evaluable: number
  completed_count: number
  total_rows: number
}

export interface EvalRun {
  run_id: string
  adapter_type: string
  trial_count: number
  status: EvalRunStatus
  scenario_ids: string[] | null
  started_at: string | null
  completed_at: string | null
  total_scenarios: number | null
  completed_scenarios: number
  error_message: string | null
  summary?: EvalRunSummary
}

export interface EvalResult {
  run_scenario_id: string
  scenario_id: string
  trial_num: number
  run_status: string
  investigation_id: string | null
  started_at: string | null
  completed_at: string | null
  run_error: string | null
  diagnostic_verdict: DiagnosticVerdict | null
  evidence_grounded: boolean | null
  uncertainty_handled: boolean | null
  tool_use_ok: boolean | null
  completed: boolean | null
  score_detail: Record<string, unknown>
  failure_reason: string | null
  evaluated_at: string | null
}

export interface FourConditionsResponse {
  scenarios: EvalScenario[]
  latest_results: Record<string, EvalResult>
}

export interface SSEEvent {
  type: 'tool_call' | 'tool_result' | 'warning' | 'complete' | 'error' | 'heartbeat' | 'done'
  tool_name?: string
  inputs?: Record<string, unknown>
  success?: boolean
  summary?: string
  sequence?: number
  message?: string
  status?: string
  tool_calls_used?: number
}
