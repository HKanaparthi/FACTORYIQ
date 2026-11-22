import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Search, ChevronRight } from 'lucide-react'
import { useTagHealth, useAlarms } from '../hooks/useAssets'
import { useCreateInvestigation } from '../hooks/useInvestigations'
import { StatusBadge } from '../components/StatusBadge'
import { TagSparkline } from '../components/TagSparkline'

const ASSETS = ['PUMP-01', 'MOTOR-01', 'CONVEYOR-01', 'FILL-01']
const ASSET_LABEL: Record<string, string> = {
  'PUMP-01': 'Centrifugal Pump',
  'MOTOR-01': 'Electric Motor',
  'CONVEYOR-01': 'Conveyor Belt',
  'FILL-01': 'Filling Station',
}
const TAG_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#a78bfa', '#f87171', '#34d399']
const TIME_RANGES = [
  { label: '15m', value: 15 },
  { label: '1h',  value: 60 },
  { label: '4h',  value: 240 },
  { label: '24h', value: 1440 },
]

export function EquipmentDetails() {
  const { assetId } = useParams<{ assetId: string }>()
  const navigate = useNavigate()
  const selectedAsset = assetId ?? 'PUMP-01'
  const [minutes, setMinutes] = useState(60)

  const { data: healthData, isLoading: loadingHealth } = useTagHealth(selectedAsset)
  const { data: alarmsData } = useAlarms(selectedAsset, 120)
  const createInv = useCreateInvestigation()

  const handleStartInvestigation = async () => {
    const result = await createInv.mutateAsync(selectedAsset)
    navigate(`/investigate?id=${result.investigation_id}`)
  }

  const tags = healthData?.tags ?? []

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>Equipment</span>
            <ChevronRight className="h-3 w-3" />
            <span className="text-slate-300">{selectedAsset}</span>
          </div>
          <h1 className="mt-1 text-xl font-semibold text-slate-100">
            {ASSET_LABEL[selectedAsset] ?? selectedAsset}
          </h1>
        </div>
        <button
          onClick={handleStartInvestigation}
          disabled={createInv.isPending}
          className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-400 transition-colors hover:bg-amber-500/20 disabled:opacity-50"
        >
          <Search className="h-4 w-4" />
          {createInv.isPending ? 'Creating…' : 'Start Investigation'}
        </button>
      </div>

      {/* Asset selector */}
      <div className="mb-6 flex gap-2">
        {ASSETS.map((a) => (
          <Link
            key={a}
            to={`/equipment/${a}`}
            className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
              a === selectedAsset
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                : 'border border-slate-800 text-slate-500 hover:border-slate-700 hover:text-slate-300'
            }`}
          >
            {a}
          </Link>
        ))}
      </div>

      {/* Tag health grid */}
      <div className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-400">Tag Health</h2>
          <div className="flex gap-1">
            {TIME_RANGES.map((r) => (
              <button
                key={r.value}
                onClick={() => setMinutes(r.value)}
                className={`rounded px-2.5 py-1 text-xs transition-colors ${
                  minutes === r.value
                    ? 'bg-slate-700 text-slate-200'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {loadingHealth ? (
          <div className="grid grid-cols-2 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-48 animate-pulse rounded-lg bg-slate-800/50" />
            ))}
          </div>
        ) : tags.length === 0 ? (
          <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-10 text-center">
            <div className="text-sm text-slate-600">No tag data available for {selectedAsset}</div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {tags.map((tag, idx) => (
              <div key={tag.tag_name} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="font-mono text-xs font-medium text-slate-200">{tag.tag_name}</div>
                  <StatusBadge status={tag.freshness_status} />
                </div>
                <TagSparkline
                  assetId={selectedAsset}
                  tagName={tag.tag_name}
                  minutes={minutes}
                  height={110}
                  color={TAG_COLORS[idx % TAG_COLORS.length]}
                />
                <div className="mt-1 text-xs text-slate-600">
                  Last update: {tag.last_update ? new Date(tag.last_update).toLocaleTimeString() : '—'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent alarms */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-slate-400">Recent Alarms (2h)</h2>
        <div className="rounded-lg border border-slate-800 bg-slate-900">
          {!alarmsData || alarmsData.alarms.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-slate-600">
              No alarms in the last 2 hours
            </div>
          ) : (
            <div className="divide-y divide-slate-800">
              {alarmsData.alarms.map((alarm) => (
                <div key={alarm.alarm_id} className="flex items-start gap-3 px-4 py-3">
                  <StatusBadge status={alarm.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-slate-300">{alarm.alarm_type}</div>
                    <div className="mt-0.5 text-xs text-slate-500">{alarm.message}</div>
                    {alarm.raw_value !== null && (
                      <div className="mt-0.5 text-xs text-slate-600">
                        Value: {alarm.raw_value?.toFixed(2)} (threshold: {alarm.threshold?.toFixed(2)})
                      </div>
                    )}
                  </div>
                  <div className="flex-shrink-0 text-xs text-slate-600">
                    {new Date(alarm.triggered_at).toLocaleTimeString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
