import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { TelemetryResponse } from '../api/types'
import { DEMO_MODE } from '../demo'
import { getDemoTelemetry } from '../demo/fixtures/telemetry'
import { useDemoPlayback } from '../demo/DemoPlaybackContext'

function useDemoPlaybackIndexSafe() {
  // Always call the hook; in non-demo mode the context returns its default value (no-op)
  return useDemoPlayback().playbackIndex
}

export function useTelemetry(assetId: string | undefined, tagName: string | undefined, minutes = 60) {
  const playbackIndex = useDemoPlaybackIndexSafe()

  return useQuery<TelemetryResponse>({
    queryKey: DEMO_MODE
      ? ['telemetry', assetId, tagName, minutes, playbackIndex]
      : ['telemetry', assetId, tagName, minutes],
    queryFn: () =>
      DEMO_MODE
        ? Promise.resolve(getDemoTelemetry(assetId!, tagName!, minutes, playbackIndex))
        : api.get(`/api/telemetry?asset_id=${assetId}&tag_name=${tagName}&minutes=${minutes}`),
    enabled: !!assetId && !!tagName,
    refetchInterval: DEMO_MODE ? false : 15_000,
  })
}
