import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AssetsResponse, TagHealthResponse, AlarmResponse } from '../api/types'

export function useAssets() {
  return useQuery<AssetsResponse>({
    queryKey: ['assets'],
    queryFn: () => api.get('/api/assets'),
    refetchInterval: 30_000,
  })
}

export function useTagHealth(assetId: string | undefined) {
  return useQuery<TagHealthResponse>({
    queryKey: ['tag-health', assetId],
    queryFn: () => api.get(`/api/tag-health?asset_id=${assetId}`),
    enabled: !!assetId,
    refetchInterval: 15_000,
  })
}

export function useAlarms(assetId?: string, sinceMinutes = 60) {
  const qs = assetId
    ? `?asset_id=${assetId}&since_minutes=${sinceMinutes}`
    : `?since_minutes=${sinceMinutes}`
  return useQuery<AlarmResponse>({
    queryKey: ['alarms', assetId, sinceMinutes],
    queryFn: () => api.get(`/api/alarms${qs}`),
    refetchInterval: 30_000,
  })
}
