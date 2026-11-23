import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  EvalRun,
  EvalResult,
  EvalScenario,
  FourConditionsResponse,
} from '../api/types'
import { DEMO_MODE } from '../demo'
import { DEMO_EVAL_RUN, getDemoEvalResults, getDemoFourConditions } from '../demo/fixtures/evalRuns'
import { DEMO_SCENARIOS } from '../demo/fixtures/scenarios'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8080'

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

export function useScenarios() {
  return useQuery<EvalScenario[]>({
    queryKey: ['eval', 'scenarios'],
    queryFn: () => DEMO_MODE ? Promise.resolve(DEMO_SCENARIOS) : fetchJson('/api/eval/scenarios'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useScenario(scenarioId: string) {
  return useQuery<EvalScenario>({
    queryKey: ['eval', 'scenarios', scenarioId],
    queryFn: () => {
      if (DEMO_MODE) {
        const s = DEMO_SCENARIOS.find(s => s.scenario_id === scenarioId)
        if (!s) throw new Error(`Scenario not found: ${scenarioId}`)
        return Promise.resolve(s)
      }
      return fetchJson(`/api/eval/scenarios/${scenarioId}`)
    },
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(scenarioId),
  })
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export function useEvalRuns() {
  return useQuery<EvalRun[]>({
    queryKey: ['eval', 'runs'],
    queryFn: () => DEMO_MODE ? Promise.resolve([DEMO_EVAL_RUN]) : fetchJson('/api/eval/runs'),
    refetchInterval: DEMO_MODE ? false : 5000,
  })
}

export function useEvalRun(runId: string) {
  return useQuery<EvalRun>({
    queryKey: ['eval', 'runs', runId],
    queryFn: () => {
      if (DEMO_MODE) return Promise.resolve(DEMO_EVAL_RUN)
      return fetchJson(`/api/eval/runs/${runId}`)
    },
    refetchInterval: DEMO_MODE ? false : (query) => {
      const data = query.state.data
      return data?.status === 'running' ? 2000 : false
    },
    enabled: Boolean(runId),
  })
}

export function useEvalResults(runId: string) {
  return useQuery<EvalResult[]>({
    queryKey: ['eval', 'runs', runId, 'results'],
    queryFn: () => {
      if (DEMO_MODE) return Promise.resolve(getDemoEvalResults(runId))
      return fetchJson(`/api/eval/runs/${runId}/results`)
    },
    refetchInterval: DEMO_MODE ? false : (query) => {
      return query.state.data?.length === 0 ? 3000 : false
    },
    enabled: Boolean(runId),
  })
}

// ---------------------------------------------------------------------------
// Start run mutation
// ---------------------------------------------------------------------------

interface StartRunPayload {
  scenario_ids?: string[] | null
  trial_count?: number
  adapter_type?: string
}

interface StartRunResponse {
  run_id: string
  status: string
}

export function useStartRun() {
  const qc = useQueryClient()
  return useMutation<StartRunResponse, Error, StartRunPayload>({
    mutationFn: async (payload) => {
      if (DEMO_MODE) {
        // In demo mode, return the pre-recorded run — no network call
        void payload
        return { run_id: DEMO_EVAL_RUN.run_id, status: 'completed' }
      }
      const r = await fetch(`${API}/api/eval/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trial_count: 1,
          adapter_type: 'scripted',
          ...payload,
        }),
      })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error((body as { detail?: string }).detail ?? `${r.status} ${r.statusText}`)
      }
      return r.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['eval', 'runs'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Four-condition comparison
// ---------------------------------------------------------------------------

export function useFourConditions() {
  return useQuery<FourConditionsResponse>({
    queryKey: ['eval', 'four-conditions'],
    queryFn: () =>
      DEMO_MODE ? Promise.resolve(getDemoFourConditions()) : fetchJson('/api/eval/four-conditions'),
    staleTime: 10 * 1000,
  })
}
