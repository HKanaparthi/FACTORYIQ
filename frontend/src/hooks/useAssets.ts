import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AssetsResponse, TagHealthResponse, AlarmResponse } from '../api/types'
import { DEMO_MODE } from '../demo'
import { DEMO_ASSETS, getDemoTagHealth, getDemoAlarms } from '../demo/fixtures/assets'

export function useAssets() {
  return useQuery<AssetsResponse>({
    queryKey: ['assets'],
    queryFn: () => DEMO_MODE ? Promise.resolve(DEMO_ASSETS) : api.get('/api/assets'),
    refetchInterval: DEMO_MODE ? false : 30_000,
  })
}

export function useTagHealth(assetId: string | undefined) {
  return useQuery<TagHealthResponse>({
    queryKey: ['tag-health', assetId],
    queryFn: () =>
      DEMO_MODE
        ? Promise.resolve(getDemoTagHealth(assetId!))
        : api.get(`/api/tag-health?asset_id=${assetId}`),
    enabled: !!assetId,
    refetchInterval: DEMO_MODE ? false : 15_000,
  })
}

export function useAlarms(assetId?: string, sinceMinutes = 60) {
  const qs = assetId
    ? `?asset_id=${assetId}&since_minutes=${sinceMinutes}`
    : `?since_minutes=${sinceMinutes}`
  return useQuery<AlarmResponse>({
    queryKey: ['alarms', assetId, sinceMinutes],
    queryFn: () =>
      DEMO_MODE
        ? Promise.resolve(getDemoAlarms(assetId, sinceMinutes))
        : api.get(`/api/alarms${qs}`),
    refetchInterval: DEMO_MODE ? false : 30_000,
  })
}
