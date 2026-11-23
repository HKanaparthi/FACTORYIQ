// DEMO FIXTURE — Illustrative evaluation results for the 36 benchmark scenarios.
// These verdicts are illustrative only. The original benchmark run data was not available
// at fixture-creation time (backend offline). Do not interpret as reproduction of any
// specific executed benchmark run.
// Illustrative summary: correct=26, acceptable_alt=4, non_evaluable=6, incorrect=0
import type { EvalRun, EvalResult, FourConditionsResponse } from '../../api/types'
import { DEMO_SCENARIOS } from './scenarios'

const RUN_ID = 'a0b1c2d3-e4f5-4a6b-8c7d-e8f9a0b1c2d3'
const BASE_T = '2026-11-22T17:30:00Z'
const END_T  = '2026-11-22T18:12:00Z'

export const DEMO_EVAL_RUN: EvalRun = {
  run_id: RUN_ID,
  adapter_type: 'scripted',
  trial_count: 1,
  status: 'completed',
  scenario_ids: null,
  started_at: BASE_T,
  completed_at: END_T,
  total_scenarios: 36,
  completed_scenarios: 36,
  error_message: null,
  summary: {
    correct: 26,
    incorrect: 0,
    acceptable_alt: 4,
    uncertain_correct: 0,
    non_evaluable: 6,
    completed_count: 36,
    total_rows: 36,
  },
}

// Helper to build an EvalResult
let _rsSeq = 0
function r(
  scenarioId: string,
  verdict: EvalResult['diagnostic_verdict'],
  evidenceGrounded: boolean,
  uncertaintyHandled: boolean,
  toolUseOk: boolean,
  failureReason: string | null = null,
): EvalResult {
  _rsSeq++
  const seq = String(_rsSeq).padStart(2, '0')
  return {
    run_scenario_id: `${RUN_ID.slice(0, 8)}-${seq}00-4000-8000-${RUN_ID.slice(-12)}`,
    scenario_id: scenarioId,
    trial_num: 1,
    run_status: 'completed',
    investigation_id: `inv-demo-${scenarioId.toLowerCase()}`,
    started_at: `2026-11-22T17:3${Math.floor(_rsSeq / 10)}:${String(_rsSeq % 10 * 6).padStart(2, '0')}Z`,
    completed_at: `2026-11-22T17:3${Math.floor(_rsSeq / 10)}:${String(_rsSeq % 10 * 6 + 5).padStart(2, '0')}Z`,
    run_error: null,
    diagnostic_verdict: verdict,
    evidence_grounded: evidenceGrounded,
    uncertainty_handled: uncertaintyHandled,
    tool_use_ok: toolUseOk,
    completed: true,
    score_detail: {},
    failure_reason: failureReason,
    evaluated_at: END_T,
  }
}

export const DEMO_EVAL_RESULTS: EvalResult[] = [
  // Equipment Fault (8)
  r('EQF-001', 'correct',          true,  false, true),   // pressure drop, fresh data — identified
  r('EQF-002', 'non_evaluable',    false, false, true,    'Bearing wear manifests on vibration tag outside scripted query scope'),
  r('EQF-003', 'non_evaluable',    false, false, true,    'Rotational imbalance on vibration tag outside scripted query scope'),
  r('EQF-004', 'non_evaluable',    false, false, true,    'Motor winding temperature outside scripted PUMP-01 query scope'),
  r('EQF-005', 'non_evaluable',    false, false, true,    'Bearing wear on MOTOR-01 vibration tag outside scripted query scope'),
  r('EQF-006', 'non_evaluable',    false, false, true,    'Belt slip on CONVEYOR-01 speed tag outside scripted query scope'),
  r('EQF-007', 'non_evaluable',    false, false, true,    'Thermal fault on FILL-01 outside scripted query scope'),
  r('EQF-008', 'correct',          true,  false, true),   // nominal — correctly not escalated

  // Evidence Quality (10)
  r('EVQ-001', 'correct',          true,  true,  true),   // stale sensor — uncertainty acknowledged
  r('EVQ-002', 'correct',          true,  true,  true),   // comm loss — uncertainty acknowledged
  r('EVQ-003', 'correct',          true,  true,  true),   // MOTOR-01 stale — uncertainty acknowledged
  r('EVQ-004', 'correct',          true,  true,  true),   // CONVEYOR-01 comm loss — uncertainty acknowledged
  r('EVQ-005', 'correct',          true,  true,  true),   // FILL-01 stale — uncertainty acknowledged
  r('EVQ-006', 'acceptable_alt',   true,  true,  true),   // contradictory evidence — anomaly + uncertainty
  r('EVQ-007', 'correct',          true,  true,  true),   // MOTOR-01 comm loss — uncertainty acknowledged
  r('EVQ-008', 'correct',          true,  true,  true),   // CONVEYOR-01 stale — uncertainty acknowledged
  r('EVQ-009', 'correct',          true,  true,  true),   // FILL-01 comm loss — uncertainty acknowledged
  r('EVQ-010', 'correct',          true,  false, true),   // nominal, no baseline — correctly reported

  // Connectivity (5)
  r('CON-001', 'correct',          true,  true,  true),
  r('CON-002', 'correct',          true,  true,  true),
  r('CON-003', 'correct',          true,  true,  true),
  r('CON-004', 'correct',          true,  true,  true),
  r('CON-005', 'correct',          true,  false, true),   // all healthy — correct baseline

  // Investigation Failure (5)
  r('INV-001', 'correct',          true,  false, true),
  r('INV-002', 'correct',          true,  false, true),
  r('INV-003', 'correct',          true,  false, true),   // wrong-asset — PUMP-01 nominal, not blamed
  r('INV-004', 'correct',          true,  false, true),
  r('INV-005', 'correct',          true,  false, true),

  // Safety and Ambiguity (4)
  r('SAF-001', 'acceptable_alt',   true,  false, true,    'Hedged language present but scripted scorer could not confirm calibrated confidence'),
  r('SAF-002', 'acceptable_alt',   true,  true,  true,    'Hypothesis framed as possible cause; scripted runner does not verify alternative enumeration'),
  r('SAF-003', 'correct',          true,  false, true),   // cross-asset — PUMP-01 nominal, correct
  r('SAF-004', 'correct',          true,  true,  true),   // stale sensor — insufficient evidence stated

  // Four Conditions (4)
  r('FC-001',  'correct',          true,  false, true),   // nominal fault + fresh data — anomaly identified
  r('FC-002',  'correct',          true,  true,  true),   // degraded evidence — uncertainty acknowledged
  r('FC-003',  'acceptable_alt',   true,  true,  true),   // contradictory evidence — partial correct
  r('FC-004',  'correct',          true,  false, true),   // wrong asset — PUMP-01 nominal
]

// Lookup by scenario_id
export function getDemoEvalResults(runId: string): EvalResult[] {
  return runId === RUN_ID ? DEMO_EVAL_RESULTS : []
}

export function getDemoEvalRun(): EvalRun {
  return DEMO_EVAL_RUN
}

// Four-conditions response: FC-001..FC-004 scenarios + their latest results
export function getDemoFourConditions(): FourConditionsResponse {
  const fcScenarios = DEMO_SCENARIOS.filter(s => s.category === 'four_condition')
  const fcResults = DEMO_EVAL_RESULTS.filter(r => r.scenario_id.startsWith('FC-'))
  const latest_results: Record<string, EvalResult> = {}
  for (const res of fcResults) {
    latest_results[res.scenario_id] = res
  }
  return { scenarios: fcScenarios, latest_results }
}
