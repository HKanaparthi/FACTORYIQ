import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Investigation, InvestigationSummary } from '../api/types'
import { DEMO_MODE } from '../demo'
import { demoStore } from '../demo/demoStore'
import {
  DEMO_INVESTIGATION_ID,
  DEMO_PUMP01_INV_ID,
  DEMO_INVESTIGATION_LIST,
  getDemoInvestigation,
  DEMO_PUMP01_INVESTIGATION,
} from '../demo/fixtures/investigations'

interface ListResponse {
  count: number
  investigations: InvestigationSummary[]
}

function buildDemoList(): ListResponse {
  const liveEntry: InvestigationSummary = {
    investigation_id: DEMO_INVESTIGATION_ID,
    asset_id: 'PUMP-01',
    status:
      demoStore.phase === 'idle'
        ? 'in_progress'
        : demoStore.phase === 'in_progress'
          ? 'in_progress'
          : (demoStore.phase as 'pending_review' | 'approved' | 'rejected'),
    started_at: new Date().toISOString(),
    completed_at: demoStore.phase === 'pending_review' ? new Date().toISOString() : null,
    has_finding: demoStore.phase === 'pending_review',
  }
  const all = demoStore.phase === 'idle'
    ? DEMO_INVESTIGATION_LIST
    : [liveEntry, ...DEMO_INVESTIGATION_LIST]
  return { count: all.length, investigations: all }
}

function buildDemoInvestigation(id: string): Investigation | null {
  if (id === DEMO_INVESTIGATION_ID) {
    const override = demoStore.getStatusOverride(id)
    const status = override ?? (demoStore.phase === 'pending_review' ? 'pending_review' : 'in_progress')
    return {
      ...DEMO_PUMP01_INVESTIGATION,
      investigation_id: DEMO_INVESTIGATION_ID,
      status,
      finding_text: status === 'pending_review' || override ? DEMO_PUMP01_INVESTIGATION.finding_text : null,
      completed_at: status === 'in_progress' ? null : DEMO_PUMP01_INVESTIGATION.completed_at,
    }
  }
  const override = demoStore.getStatusOverride(id)
  const base = getDemoInvestigation(id)
  if (!base) return null
  return override ? { ...base, status: override } : base
}

export function useInvestigations(status?: string) {
  const qs = status ? `?status=${status}` : ''
  return useQuery<ListResponse>({
    queryKey: ['investigations', status, demoStore.phase],
    queryFn: () => {
      if (DEMO_MODE) {
        const result = buildDemoList()
        const filtered = status
          ? { ...result, investigations: result.investigations.filter(i => i.status === status), count: 0 }
          : result
        filtered.count = filtered.investigations.length
        return Promise.resolve(filtered)
      }
      return api.get(`/api/investigations${qs}`)
    },
    refetchInterval: DEMO_MODE ? 1000 : 10_000,
  })
}

export function useInvestigation(id: string | null) {
  return useQuery<Investigation>({
    queryKey: ['investigation', id, demoStore.phase],
    queryFn: () => {
      if (DEMO_MODE) {
        const inv = buildDemoInvestigation(id!)
        if (!inv) throw new Error(`Demo investigation not found: ${id}`)
        return Promise.resolve(inv)
      }
      return api.get(`/api/investigations/${id}`)
    },
    enabled: !!id,
    refetchInterval: DEMO_MODE ? 1000 : 5_000,
  })
}

export function useCreateInvestigation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (assetId: string) => {
      if (DEMO_MODE) {
        demoStore.phase = 'in_progress'
        return Promise.resolve({
          investigation_id: DEMO_INVESTIGATION_ID,
          asset_id: assetId,
          status: 'in_progress',
          started_at: new Date().toISOString(),
        })
      }
      return api.post<{ investigation_id: string; asset_id: string; status: string; started_at: string }>(
        '/api/investigations',
        { asset_id: assetId },
      )
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['investigations'] })
      qc.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}

export function useScriptedRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (investigationId: string) => {
      if (DEMO_MODE) {
        return Promise.resolve({
          investigation_id: investigationId,
          status: 'in_progress',
          mode: 'scripted_demo',
          stream_url: `/api/investigations/${investigationId}/stream`,
        })
      }
      return api.post<{ investigation_id: string; status: string; mode: string; stream_url: string }>(
        `/api/investigations/${investigationId}/scripted-run`,
      )
    },
    onSuccess: (_data, investigationId) => {
      qc.invalidateQueries({ queryKey: ['investigation', investigationId] })
    },
  })
}

export function useReviewInvestigation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      investigationId,
      action,
      notes: _notes,
      password: _password,
    }: {
      investigationId: string
      action: 'approve' | 'reject'
      notes?: string
      password: string
    }) => {
      if (DEMO_MODE) {
        const status = action === 'approve' ? 'approved' : 'rejected'
        demoStore.setStatusOverride(investigationId, status)
        if (investigationId === DEMO_INVESTIGATION_ID || investigationId === DEMO_PUMP01_INV_ID) {
          demoStore.phase = status
        }
        return Promise.resolve({ investigation_id: investigationId, status })
      }
      return api.post<{ investigation_id: string; status: string; notes?: string }>(
        `/api/investigations/${investigationId}/review`,
        { action, notes: _notes, password: _password },
      )
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['investigation', vars.investigationId] })
      qc.invalidateQueries({ queryKey: ['investigations'] })
      qc.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}
