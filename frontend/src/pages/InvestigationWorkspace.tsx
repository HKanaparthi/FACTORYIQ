import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  Search,
  CheckCircle,
  XCircle,
  Terminal,
  ChevronRight,
  AlertCircle,
  ChevronDown,
  Loader2,
} from 'lucide-react'
import {
  useCreateInvestigation,
  useScriptedRun,
  useInvestigation,
} from '../hooks/useInvestigations'
import { useSSE } from '../hooks/useSSE'
import { StatusBadge } from '../components/StatusBadge'
import { FindingReport } from '../components/FindingReport'
import type { SSEEvent } from '../api/types'

const ASSETS = ['PUMP-01', 'MOTOR-01', 'CONVEYOR-01', 'FILL-01']

const TOOL_LABELS: Record<string, { label: string; desc: string }> = {
  get_recent_events:    { label: 'Recent Events',      desc: 'Fetching alarm & event history' },
  check_data_quality:   { label: 'Data Quality',       desc: 'Checking tag freshness & OPC quality' },
  query_telemetry:      { label: 'Telemetry Query',    desc: 'Retrieving time-series sensor data' },
  compare_baseline:     { label: 'Baseline Comparison',desc: 'Comparing to 7-day historical baseline' },
  query_equipment_docs: { label: 'Equipment Docs',     desc: 'Searching maintenance documentation' },
  flag_for_review:      { label: 'Submit Finding',     desc: 'Sending finding for human review' },
}

// ---------------------------------------------------------------------------
// Individual event row in the timeline
// ---------------------------------------------------------------------------

function ToolCallPair({
  callEvent,
  resultEvent,
}: {
  callEvent: SSEEvent
  resultEvent: SSEEvent | undefined
}) {
  const [expanded, setExpanded] = useState(false)
  const toolInfo = TOOL_LABELS[callEvent.tool_name ?? '']
  const isFlagForReview = callEvent.tool_name === 'flag_for_review'
  const isRunning = !resultEvent
  const success = resultEvent?.success !== false

  return (
    <div className="border-b border-slate-800/50 last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-slate-800/20"
        disabled={isFlagForReview && !resultEvent?.summary}
      >
        {/* Sequence indicator */}
        <div className="mt-0.5 flex-shrink-0">
          {isRunning ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
          ) : success ? (
            <CheckCircle className="h-4 w-4 text-emerald-500" />
          ) : (
            <XCircle className="h-4 w-4 text-red-500" />
          )}
        </div>

        {/* Tool info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-200">
              {toolInfo?.label ?? callEvent.tool_name}
            </span>
            {callEvent.sequence !== undefined && (
              <span className="text-xs text-slate-600">#{callEvent.sequence}</span>
            )}
            {isRunning && (
              <span className="text-xs text-blue-400">running…</span>
            )}
          </div>

          {/* Summary line from result */}
          {resultEvent?.summary && (
            <div className="mt-0.5 text-xs text-slate-500">
              {isFlagForReview ? (
                <span className="text-emerald-400">{resultEvent.summary}</span>
              ) : (
                resultEvent.summary
              )}
            </div>
          )}

          {/* Inputs preview (non-flag_for_review only) */}
          {!isFlagForReview && callEvent.inputs && Object.keys(callEvent.inputs).length > 0 && (
            <div className="mt-0.5 font-mono text-xs text-slate-700">
              {Object.entries(callEvent.inputs)
                .filter(([k]) => k !== 'investigation_id')
                .slice(0, 3)
                .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
                .join('  ')}
            </div>
          )}
        </div>

        {/* Expand toggle for non-flag events */}
        {!isFlagForReview && resultEvent && (
          <div className="flex-shrink-0">
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-slate-600" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-slate-600" />
            )}
          </div>
        )}
      </button>

      {/* Expanded detail */}
      {expanded && !isFlagForReview && (
        <div className="border-t border-slate-800/30 bg-slate-950/50 px-4 py-3">
          {callEvent.inputs && Object.keys(callEvent.inputs).filter(k => k !== 'investigation_id').length > 0 && (
            <div className="mb-2">
              <div className="mb-1 text-xs font-medium text-slate-600">Tool inputs</div>
              <pre className="rounded bg-slate-900 p-2 font-mono text-xs text-slate-500">
                {JSON.stringify(
                  Object.fromEntries(
                    Object.entries(callEvent.inputs).filter(([k]) => k !== 'investigation_id')
                  ),
                  null, 2
                )}
              </pre>
            </div>
          )}
          <div className="text-xs text-slate-600">
            {toolInfo?.desc ?? callEvent.tool_name}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status / terminal events
// ---------------------------------------------------------------------------

function TerminalEventRow({ event }: { event: SSEEvent }) {
  if (event.type === 'complete') {
    return (
      <div className="mx-4 my-2 flex items-center gap-2 rounded border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
        <CheckCircle className="h-4 w-4 flex-shrink-0 text-emerald-400" />
        <span className="text-xs text-emerald-400">
          Investigation complete · {event.tool_calls_used} tool calls · pending human review
        </span>
      </div>
    )
  }
  if (event.type === 'error') {
    return (
      <div className="mx-4 my-2 flex items-center gap-2 rounded border border-red-500/20 bg-red-500/5 px-3 py-2">
        <XCircle className="h-4 w-4 flex-shrink-0 text-red-400" />
        <span className="text-xs text-red-400">{event.message}</span>
      </div>
    )
  }
  if (event.type === 'warning') {
    return (
      <div className="mx-4 my-2 flex items-center gap-2 rounded border border-amber-500/20 bg-amber-500/5 px-3 py-2">
        <AlertCircle className="h-4 w-4 flex-shrink-0 text-amber-400" />
        <span className="text-xs text-amber-400">{event.message}</span>
      </div>
    )
  }
  return null
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function InvestigationWorkspace() {
  const [searchParams] = useSearchParams()
  const preloadedId = searchParams.get('id')
  const preloadedAsset = searchParams.get('asset')

  const [selectedAsset, setSelectedAsset] = useState(
    preloadedAsset && ASSETS.includes(preloadedAsset) ? preloadedAsset : 'PUMP-01'
  )
  const [activeInvId, setActiveInvId] = useState<string | null>(preloadedId)
  const [phase, setPhase] = useState<'idle' | 'created' | 'running' | 'done'>(
    preloadedId ? 'created' : 'idle',
  )

  const createInv = useCreateInvestigation()
  const scriptedRun = useScriptedRun()
  const { data: invData, refetch: refetchInv } = useInvestigation(activeInvId)
  const { events, connected, done: sseDone, connect, disconnect } = useSSE(null)

  useEffect(() => {
    if (preloadedId) {
      setActiveInvId(preloadedId)
      setPhase('created')
    }
  }, [preloadedId])

  useEffect(() => {
    if (sseDone) {
      setPhase('done')
      refetchInv()
    }
  }, [sseDone, refetchInv])

  const handleCreate = async () => {
    const result = await createInv.mutateAsync(selectedAsset)
    setActiveInvId(result.investigation_id)
    setPhase('created')
  }

  const handleRun = async () => {
    if (!activeInvId) return
    setPhase('running')
    connect(activeInvId)
    await scriptedRun.mutateAsync(activeInvId)
  }

  const handleReset = () => {
    disconnect()
    setActiveInvId(null)
    setPhase('idle')
  }

  // Pair up tool_call and tool_result events
  const toolPairs: Array<{ call: SSEEvent; result?: SSEEvent }> = []
  const terminalEvents: SSEEvent[] = []

  for (const ev of events) {
    if (ev.type === 'tool_call') {
      toolPairs.push({ call: ev })
    } else if (ev.type === 'tool_result') {
      const last = toolPairs[toolPairs.length - 1]
      if (last && !last.result) last.result = ev
    } else if (['complete', 'error', 'warning', 'done'].includes(ev.type)) {
      terminalEvents.push(ev)
    }
  }

  const isComplete =
    invData?.status === 'pending_review' ||
    invData?.status === 'approved' ||
    invData?.status === 'rejected'

  return (
    <div className="flex h-full">
      {/* ── Left control panel ── */}
      <div className="flex w-72 flex-shrink-0 flex-col border-r border-slate-800">
        <div className="border-b border-slate-800 p-4">
          <h1 className="text-base font-semibold text-slate-100">AI Investigation</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Scripted runner · zero API cost · real MCP tools
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {/* Phase: idle */}
          {phase === 'idle' && (
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-slate-400">Asset</label>
                <select
                  value={selectedAsset}
                  onChange={(e) => setSelectedAsset(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-amber-500/50 focus:outline-none"
                >
                  {ASSETS.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <button
                onClick={handleCreate}
                disabled={createInv.isPending}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 py-2.5 text-sm font-medium text-amber-400 hover:bg-amber-500/20 disabled:opacity-50"
              >
                <Search className="h-4 w-4" />
                {createInv.isPending ? 'Creating…' : 'Create Investigation'}
              </button>
            </div>
          )}

          {/* Phase: created */}
          {phase === 'created' && activeInvId && (
            <div className="space-y-3">
              {invData && (
                <div className="rounded border border-slate-700 bg-slate-800/50 p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Asset</span>
                    <span className="font-mono text-xs font-medium text-amber-400">{invData.asset_id}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Status</span>
                    <StatusBadge status={invData.status} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">ID</span>
                    <span className="font-mono text-xs text-slate-600 truncate max-w-[140px]">{activeInvId.slice(0, 18)}…</span>
                  </div>
                </div>
              )}
              <button
                onClick={handleRun}
                disabled={scriptedRun.isPending || invData?.status !== 'in_progress'}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 py-2.5 text-sm font-medium text-blue-400 hover:bg-blue-500/20 disabled:opacity-50"
              >
                {scriptedRun.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Starting…</>
                ) : (
                  'Run Scripted Agent'
                )}
              </button>
              <button onClick={handleReset} className="w-full py-1.5 text-xs text-slate-600 hover:text-slate-400">
                Start over
              </button>
            </div>
          )}

          {/* Phase: running / done */}
          {(phase === 'running' || phase === 'done') && invData && (
            <div className="space-y-3">
              <div className="rounded border border-slate-700 bg-slate-800/50 p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-medium text-amber-400">{invData.asset_id}</span>
                  <StatusBadge status={invData.status} />
                </div>
                {invData.agent_tool_calls && (
                  <div className="text-xs text-slate-500">
                    {invData.agent_tool_calls} tool calls · {invData.agent_model}
                  </div>
                )}
              </div>

              {connected && (
                <div className="flex items-center gap-2 text-xs text-blue-400">
                  <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
                  Agent running…
                </div>
              )}

              {phase === 'done' && isComplete && (
                <div className="space-y-2">
                  <Link
                    to={`/evidence?id=${activeInvId}`}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-800 py-2 text-sm text-slate-300 hover:bg-slate-700"
                  >
                    View Evidence <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                  {invData?.status === 'pending_review' && (
                    <Link
                      to={`/review?id=${activeInvId}`}
                      className="flex w-full items-center justify-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 py-2 text-sm text-amber-400 hover:bg-amber-500/20"
                    >
                      Review Finding <ChevronRight className="h-3.5 w-3.5" />
                    </Link>
                  )}
                  <button onClick={handleReset} className="w-full py-1.5 text-xs text-slate-600 hover:text-slate-400">
                    New investigation
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Right: timeline + finding ── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Timeline */}
        <div className="flex-1 overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/90 px-4 py-2.5 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">
                {toolPairs.length > 0
                  ? `Agent Activity · ${toolPairs.length} tool calls`
                  : 'Waiting for agent…'}
              </span>
              {invData && (
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-amber-400">{invData.asset_id}</span>
                  <StatusBadge status={invData.status} />
                </div>
              )}
            </div>
          </div>

          {/* Empty state */}
          {toolPairs.length === 0 && (
            <div className="flex h-48 items-center justify-center">
              <div className="text-center">
                <Terminal className="mx-auto mb-2 h-8 w-8 text-slate-800" />
                <div className="text-sm text-slate-700">
                  {phase === 'idle' ? 'Select an asset and start an investigation' : 'Starting agent…'}
                </div>
              </div>
            </div>
          )}

          {/* Tool call pairs */}
          <div className="divide-y divide-slate-800/0">
            {toolPairs.map((pair, i) => (
              <ToolCallPair key={i} callEvent={pair.call} resultEvent={pair.result} />
            ))}
          </div>

          {/* Terminal events */}
          {terminalEvents.map((ev, i) => (
            <TerminalEventRow key={i} event={ev} />
          ))}
        </div>

        {/* Finding panel */}
        {invData?.finding_text && (
          <div className="max-h-[55vh] overflow-y-auto border-t border-slate-800">
            <div className="border-b border-slate-800 px-4 py-2">
              <span className="text-xs font-medium text-slate-500">Investigation Finding</span>
            </div>
            <div className="p-4">
              <FindingReport investigation={invData} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
