import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle, Activity, Search, Clock, Zap } from 'lucide-react'
import { useAssets, useAlarms } from '../hooks/useAssets'
import { useInvestigations } from '../hooks/useInvestigations'
import { StatusBadge } from '../components/StatusBadge'
import type { AssetSummary } from '../api/types'

const HEALTH_EXPLANATION: Record<string, string> = {
  HEALTHY:  'All tags fresh, no active alarms',
  WARNING:  'Active HIGH/CRITICAL alarms',
  DEGRADED: 'Stale or missing sensor tags',
  UNKNOWN:  'No telemetry data',
}

function AssetCard({ asset }: { asset: AssetSummary }) {
  const borderColor =
    asset.health_status === 'WARNING'
      ? 'border-orange-500/30 hover:border-orange-500/50'
      : asset.health_status === 'DEGRADED'
      ? 'border-amber-500/20 hover:border-amber-500/40'
      : 'border-slate-800 hover:border-slate-700'

  return (
    <div className={`rounded-lg border bg-slate-900 p-4 transition-colors ${borderColor}`}>
      <div className="mb-3 flex items-start justify-between">
        <div>
          <Link
            to={`/equipment/${asset.asset_id}`}
            className="font-mono text-sm font-semibold text-slate-100 hover:text-amber-400 transition-colors"
          >
            {asset.asset_id}
          </Link>
          <div className="text-xs text-slate-500">{asset.label}</div>
        </div>
        <StatusBadge status={asset.health_status} />
      </div>

      <div className="mb-2 text-xs text-slate-600">
        {HEALTH_EXPLANATION[asset.health_status] ?? asset.health_status}
      </div>

      <div className="mb-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded bg-slate-800/50 py-1.5">
          <div className="text-sm font-semibold text-emerald-400">{asset.fresh_tags}</div>
          <div className="text-xs text-slate-500">Fresh</div>
        </div>
        <div className="rounded bg-slate-800/50 py-1.5">
          <div className={`text-sm font-semibold ${asset.stale_tags > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
            {asset.stale_tags}
          </div>
          <div className="text-xs text-slate-500">Stale</div>
        </div>
        <div className="rounded bg-slate-800/50 py-1.5">
          <div className={`text-sm font-semibold ${asset.recent_alarms > 0 ? 'text-red-400' : 'text-slate-400'}`}>
            {asset.recent_alarms}
          </div>
          <div className="text-xs text-slate-500">Alarms</div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Link
          to={`/equipment/${asset.asset_id}`}
          className="flex flex-1 items-center justify-center gap-1 rounded border border-slate-700 bg-slate-800 py-1.5 text-xs text-slate-400 hover:bg-slate-700 transition-colors"
        >
          Details
        </Link>
        <Link
          to={`/investigate?asset=${asset.asset_id}`}
          className="flex flex-1 items-center justify-center gap-1 rounded border border-amber-500/30 bg-amber-500/10 py-1.5 text-xs text-amber-400 hover:bg-amber-500/20 transition-colors"
        >
          <Search className="h-3 w-3" />
          Investigate
        </Link>
      </div>

      {asset.latest_investigation_status && (
        <div className="mt-2 flex items-center justify-between border-t border-slate-800 pt-2">
          <span className="text-xs text-slate-500">Latest investigation</span>
          {asset.latest_investigation_id ? (
            <Link to={`/evidence?id=${asset.latest_investigation_id}`}>
              <StatusBadge status={asset.latest_investigation_status} />
            </Link>
          ) : (
            <StatusBadge status={asset.latest_investigation_status} />
          )}
        </div>
      )}
    </div>
  )
}

const SEVERITY_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }

export function OperationsOverview() {
  const { data: assetsData, isLoading: loadingAssets } = useAssets()
  const { data: alarmsData } = useAlarms(undefined, 60)
  const { data: invData } = useInvestigations()

  const now = Date.now()
  const recentPending = invData?.investigations.filter(
    (i) => i.status === 'pending_review' && now - new Date(i.started_at).getTime() < 24 * 3600 * 1000
  ) ?? []
  const totalPending = invData?.investigations.filter((i) => i.status === 'pending_review').length ?? 0
  const activeCount = invData?.investigations.filter((i) => i.status === 'in_progress').length ?? 0
  const totalAlarms = alarmsData?.count ?? 0

  const sortedAlarms = [...(alarmsData?.alarms ?? [])].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
  )

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Operations Overview</h1>
        <p className="mt-1 text-sm text-slate-500">Real-time monitoring · Simulated plant data</p>
      </div>

      {/* Top metrics */}
      <div className="mb-6 grid grid-cols-4 gap-4">
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="mb-1 flex items-center gap-2">
            <Activity className="h-4 w-4 text-blue-400" />
            <span className="text-xs text-slate-500">Active Investigations</span>
          </div>
          <div className="text-2xl font-semibold text-blue-400">{activeCount}</div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="mb-1 flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-400" />
            <span className="text-xs text-slate-500">Pending Review (24h)</span>
          </div>
          <div className="text-2xl font-semibold text-amber-400">{recentPending.length}</div>
          {totalPending > recentPending.length && (
            <div className="mt-0.5 text-xs text-slate-600">{totalPending} total</div>
          )}
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="mb-1 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-orange-400" />
            <span className="text-xs text-slate-500">Alarms (1h)</span>
          </div>
          <div className="text-2xl font-semibold text-orange-400">{totalAlarms}</div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="mb-1 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-400" />
            <span className="text-xs text-slate-500">Assets Monitored</span>
          </div>
          <div className="text-2xl font-semibold text-emerald-400">
            {assetsData?.assets.length ?? 0}
          </div>
        </div>
      </div>

      {/* Asset grid */}
      <div className="mb-6">
        <h2 className="mb-3 text-sm font-medium text-slate-400">Asset Health</h2>
        {loadingAssets ? (
          <div className="grid grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-44 animate-pulse rounded-lg bg-slate-800/50" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-4">
            {assetsData?.assets.map((asset) => (
              <AssetCard key={asset.asset_id} asset={asset} />
            ))}
          </div>
        )}
      </div>

      {/* Recent alarms */}
      <div className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-400">Recent Alarms (1h)</h2>
          <span className="text-xs text-slate-600">{totalAlarms} events</span>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900">
          {sortedAlarms.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-slate-600">No recent alarms</div>
          ) : (
            <div className="divide-y divide-slate-800">
              {sortedAlarms.slice(0, 10).map((alarm) => (
                <div key={alarm.alarm_id} className="flex items-start gap-3 px-4 py-3">
                  <StatusBadge status={alarm.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-amber-400">{alarm.asset_id}</span>
                      <span className="text-xs text-slate-500">{alarm.alarm_type}</span>
                    </div>
                    <div className="mt-0.5 truncate text-xs text-slate-400">{alarm.message}</div>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-2">
                    <span className="text-xs text-slate-600">
                      {new Date(alarm.triggered_at).toLocaleTimeString()}
                    </span>
                    <Link
                      to={`/investigate?asset=${alarm.asset_id}`}
                      className="flex items-center gap-1 rounded border border-amber-500/20 bg-amber-500/5 px-2 py-0.5 text-xs text-amber-500 hover:bg-amber-500/15 transition-colors"
                    >
                      <Zap className="h-3 w-3" />
                      Investigate
                    </Link>
                  </div>
                </div>
              ))}
              {sortedAlarms.length > 10 && (
                <div className="px-4 py-2 text-center text-xs text-slate-600">
                  +{sortedAlarms.length - 10} more alarms not shown
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex gap-3">
        <Link
          to="/investigate"
          className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-400 transition-colors hover:bg-amber-500/20"
        >
          <Search className="h-4 w-4" />
          Start Investigation
        </Link>
        {totalPending > 0 && (
          <Link
            to="/review"
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-300 transition-colors hover:bg-slate-700"
          >
            <Clock className="h-4 w-4 text-amber-400" />
            Review {recentPending.length > 0 ? recentPending.length : totalPending} Finding{(recentPending.length || totalPending) !== 1 ? 's' : ''}
          </Link>
        )}
      </div>
    </div>
  )
}
