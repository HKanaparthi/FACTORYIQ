import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, Database } from 'lucide-react'
import { useInvestigations, useInvestigation } from '../hooks/useInvestigations'
import { StatusBadge } from '../components/StatusBadge'
import { TierBadge } from '../components/TierBadge'
import { FindingReport } from '../components/FindingReport'

function EvidenceRow({ item }: { item: NonNullable<ReturnType<typeof useInvestigation>['data']>['evidence_items'][0] }) {
  const [expanded, setExpanded] = useState(false)

  const TOOL_LABELS: Record<string, string> = {
    get_recent_events:    'Recent Events',
    check_data_quality:   'Data Quality',
    query_telemetry:      'Telemetry Query',
    compare_baseline:     'Baseline Comparison',
    query_equipment_docs: 'Equipment Docs',
    flag_for_review:      'Flag for Review',
  }

  const filteredInputs = item.tool_inputs
    ? Object.fromEntries(Object.entries(item.tool_inputs).filter(([k]) => k !== 'investigation_id'))
    : null

  return (
    <div className="border-b border-slate-800 last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-3 p-3 text-left hover:bg-slate-800/30"
      >
        <div className="mt-0.5 flex-shrink-0 font-mono text-xs text-slate-600">
          #{item.sequence_num.toString().padStart(2, '0')}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-medium text-slate-200">
              {TOOL_LABELS[item.tool_name] ?? item.tool_name}
            </span>
            <TierBadge tier={item.evidence_tier} compact />
          </div>
          {item.citation_text && (
            <div className="mt-0.5 text-xs text-slate-500 line-clamp-1">{item.citation_text}</div>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <span className="text-xs text-slate-600">
            {new Date(item.recorded_at).toLocaleTimeString()}
          </span>
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-800/50 bg-slate-950/50 px-4 py-3 space-y-3">
          {filteredInputs && Object.keys(filteredInputs).length > 0 && (
            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">Inputs</div>
              <pre className="rounded bg-slate-900 p-2 font-mono text-xs text-slate-400 overflow-x-auto">
                {JSON.stringify(filteredInputs, null, 2)}
              </pre>
            </div>
          )}

          {item.tool_output && Object.keys(item.tool_output).length > 0 && (
            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">MCP Response</div>
              <pre className="rounded bg-slate-900 p-2 font-mono text-xs text-slate-400 overflow-x-auto max-h-48">
                {JSON.stringify(item.tool_output, null, 2)}
              </pre>
            </div>
          )}

          <div>
            <div className="mb-1 text-xs font-medium text-slate-500">Evidence Tier</div>
            <TierBadge tier={item.evidence_tier} />
          </div>

          {item.citation_text && (
            <div>
              <div className="mb-1 text-xs font-medium text-slate-500">Citation</div>
              <div className="text-xs text-slate-400">{item.citation_text}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function EvidenceExplorer() {
  const [searchParams, setSearchParams] = useSearchParams()
  const preloadedId = searchParams.get('id')
  const [selectedId, setSelectedId] = useState<string | null>(preloadedId)

  const { data: listData, isLoading: listLoading } = useInvestigations()
  const { data: invData, isLoading: invLoading } = useInvestigation(selectedId)

  const handleSelect = (id: string) => {
    setSelectedId(id)
    setSearchParams({ id })
  }

  return (
    <div className="flex h-full">
      {/* Left: investigation list */}
      <div className="flex w-72 flex-shrink-0 flex-col border-r border-slate-800">
        <div className="border-b border-slate-800 p-4">
          <h1 className="text-lg font-semibold text-slate-100">Evidence Explorer</h1>
          <p className="mt-0.5 text-xs text-slate-500">{listData?.count ?? 0} investigations</p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {listLoading ? (
            <div className="p-4 text-xs text-slate-600">Loading…</div>
          ) : listData?.investigations.length === 0 ? (
            <div className="p-4 text-center text-sm text-slate-600">
              No investigations yet.{' '}
              <Link to="/investigate" className="text-amber-400 hover:underline">
                Start one
              </Link>
            </div>
          ) : (
            listData?.investigations.map((inv) => (
              <button
                key={inv.investigation_id}
                onClick={() => handleSelect(inv.investigation_id)}
                className={`flex w-full flex-col gap-1 border-b border-slate-800/50 p-3 text-left transition-colors hover:bg-slate-800/30 ${
                  selectedId === inv.investigation_id ? 'bg-amber-500/5 border-l-2 border-l-amber-500/50' : ''
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-medium text-amber-400">{inv.asset_id}</span>
                  <StatusBadge status={inv.status} />
                </div>
                <div className="font-mono text-xs text-slate-600 truncate">
                  {inv.investigation_id.substring(0, 16)}…
                </div>
                <div className="text-xs text-slate-600">
                  {new Date(inv.started_at).toLocaleString()}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right: evidence items */}
      <div className="flex-1 overflow-y-auto">
        {!selectedId ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <Database className="mx-auto mb-3 h-10 w-10 text-slate-700" />
              <div className="text-sm text-slate-600">Select an investigation to view evidence</div>
            </div>
          </div>
        ) : invLoading ? (
          <div className="p-6">
            <div className="space-y-2">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-slate-800/50" />
              ))}
            </div>
          </div>
        ) : invData ? (
          <div>
            {/* Investigation header */}
            <div className="border-b border-slate-800 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-semibold text-slate-100">
                      {invData.asset_id}
                    </span>
                    <StatusBadge status={invData.status} />
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-slate-500">
                    {invData.investigation_id}
                  </div>
                </div>
                <div className="text-right text-xs text-slate-600">
                  <div>{invData.agent_model ?? 'unknown'}</div>
                  {invData.agent_tool_calls != null && (
                    <div>{invData.agent_tool_calls} tool calls</div>
                  )}
                </div>
              </div>
              {invData.agent_error && (
                <div className="mt-2 rounded border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-400">
                  {invData.agent_error}
                </div>
              )}
            </div>

            {/* Evidence items */}
            <div className="p-4">
              <div className="mb-3 text-xs font-medium text-slate-500">
                Evidence Chain · {invData.evidence_items.length} items
              </div>
              {invData.evidence_items.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-800 px-4 py-8 text-center text-sm text-slate-600">
                  No evidence items recorded
                </div>
              ) : (
                <div className="rounded-lg border border-slate-800 bg-slate-900">
                  {invData.evidence_items.map((item) => (
                    <EvidenceRow key={item.evidence_id} item={item} />
                  ))}
                </div>
              )}
            </div>

            {/* Finding */}
            {invData.finding_text && (
              <div className="px-4 pb-6">
                <div className="mb-3 text-xs font-medium text-slate-500">Investigation Finding</div>
                <FindingReport investigation={invData} />
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}
