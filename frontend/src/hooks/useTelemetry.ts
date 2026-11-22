import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { TelemetryResponse } from '../api/types'

export function useTelemetry(assetId: string | undefined, tagName: string | undefined, minutes = 60) {
  return useQuery<TelemetryResponse>({
    queryKey: ['telemetry', assetId, tagName, minutes],
    queryFn: () =>
      api.get(`/api/telemetry?asset_id=${assetId}&tag_name=${tagName}&minutes=${minutes}`),
    enabled: !!assetId && !!tagName,
    refetchInterval: 15_000,
  })
}
