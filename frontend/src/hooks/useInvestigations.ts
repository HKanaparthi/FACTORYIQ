import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Investigation, InvestigationSummary } from '../api/types'

interface ListResponse {
  count: number
  investigations: InvestigationSummary[]
}

export function useInvestigations(status?: string) {
  const qs = status ? `?status=${status}` : ''
  return useQuery<ListResponse>({
    queryKey: ['investigations', status],
    queryFn: () => api.get(`/api/investigations${qs}`),
    refetchInterval: 10_000,
  })
}

export function useInvestigation(id: string | null) {
  return useQuery<Investigation>({
    queryKey: ['investigation', id],
    queryFn: () => api.get(`/api/investigations/${id}`),
    enabled: !!id,
    refetchInterval: 5_000,
  })
}

export function useCreateInvestigation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (assetId: string) =>
      api.post<{ investigation_id: string; asset_id: string; status: string; started_at: string }>(
        '/api/investigations',
        { asset_id: assetId },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['investigations'] })
      qc.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}

export function useScriptedRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (investigationId: string) =>
      api.post<{ investigation_id: string; status: string; mode: string; stream_url: string }>(
        `/api/investigations/${investigationId}/scripted-run`,
      ),
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
      notes,
      password,
    }: {
      investigationId: string
      action: 'approve' | 'reject'
      notes?: string
      password: string
    }) =>
      api.post<{ investigation_id: string; status: string; notes?: string }>(
        `/api/investigations/${investigationId}/review`,
        { action, notes, password },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['investigation', vars.investigationId] })
      qc.invalidateQueries({ queryKey: ['investigations'] })
      qc.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}
