import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { CheckCircle, XCircle, Lock, Eye, EyeOff, AlertCircle } from 'lucide-react'
import { useInvestigations, useInvestigation, useReviewInvestigation } from '../hooks/useInvestigations'
import { StatusBadge } from '../components/StatusBadge'
import { FindingReport } from '../components/FindingReport'
import { DEMO_MODE } from '../demo'

export function HumanReview() {
  const [searchParams, setSearchParams] = useSearchParams()
  const preloadedId = searchParams.get('id')
  const [selectedId, setSelectedId] = useState<string | null>(preloadedId)
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [notes, setNotes] = useState('')
  const [lastResult, setLastResult] = useState<{ action: string; status: string } | null>(null)
  const [showAll, setShowAll] = useState(false)

  const { data: listData } = useInvestigations('pending_review')
  const { data: invData, isLoading } = useInvestigation(selectedId)
  const reviewMutation = useReviewInvestigation()

  const allPending = listData?.investigations ?? []
  const now = Date.now()
  const recentPending = allPending.filter(
    (i) => now - new Date(i.started_at).getTime() < 24 * 3600 * 1000
  )
  const pendingList = showAll ? allPending : recentPending.length > 0 ? recentPending : allPending

  const handleSelect = (id: string) => {
    setSelectedId(id)
    setSearchParams({ id })
    setLastResult(null)
    setPassword('')
    setNotes('')
  }

  const handleReview = async (action: 'approve' | 'reject') => {
    if (!selectedId) return
    if (!DEMO_MODE && !password) return
    try {
      const result = await reviewMutation.mutateAsync({
        investigationId: selectedId,
        action,
        notes,
        password,
      })
      setLastResult({ action, status: result.status })
      setPassword('')
    } catch {
      // error shown via reviewMutation.error
    }
  }

  return (
    <div className="flex h-full">
      {/* Left: pending investigations */}
      <div className="flex w-72 flex-shrink-0 flex-col border-r border-slate-800">
        <div className="border-b border-slate-800 p-4">
          <h1 className="text-lg font-semibold text-slate-100">Human Review</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {showAll ? allPending.length : recentPending.length > 0 ? recentPending.length : allPending.length} pending
            {!showAll && allPending.length > recentPending.length && (
              <span className="ml-1 text-slate-600">(24h view)</span>
            )}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto">
          {pendingList.length === 0 ? (
            <div className="p-6 text-center">
              <CheckCircle className="mx-auto mb-2 h-8 w-8 text-slate-700" />
              <div className="text-sm text-slate-500">No investigations pending review</div>
              <Link to="/investigate" className="mt-2 block text-xs text-amber-400 hover:underline">
                Start an investigation
              </Link>
            </div>
          ) : (
            pendingList.map((inv) => (
              <button
                key={inv.investigation_id}
                onClick={() => handleSelect(inv.investigation_id)}
                className={`flex w-full flex-col gap-1 border-b border-slate-800/50 p-3 text-left transition-colors hover:bg-slate-800/30 ${
                  selectedId === inv.investigation_id
                    ? 'bg-amber-500/5 border-l-2 border-l-amber-500/50'
                    : ''
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

        {/* Show all / show recent toggle */}
        {allPending.length > recentPending.length && (
          <div className="border-t border-slate-800 p-3">
            <button
              onClick={() => setShowAll(!showAll)}
              className="w-full text-center text-xs text-slate-500 hover:text-slate-300"
            >
              {showAll
                ? `Show recent only (${recentPending.length})`
                : `Show all (${allPending.length} total)`}
            </button>
          </div>
        )}
      </div>

      {/* Right: review panel */}
      <div className="flex-1 overflow-y-auto">
        {!selectedId ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <Lock className="mx-auto mb-3 h-10 w-10 text-slate-700" />
              <div className="text-sm text-slate-500">Select an investigation to review</div>
              <div className="mt-1 text-xs text-slate-600">
                Human approval requires the review password
              </div>
            </div>
          </div>
        ) : isLoading ? (
          <div className="p-6 text-sm text-slate-600">Loading…</div>
        ) : invData ? (
          <div className="p-6">
            {/* Investigation info */}
            <div className="mb-5 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-semibold text-slate-100">
                    {invData.asset_id}
                  </span>
                  <StatusBadge status={invData.status} size="md" />
                </div>
                <div className="mt-0.5 font-mono text-xs text-slate-500">
                  {invData.investigation_id}
                </div>
              </div>
              <div className="text-right text-xs text-slate-600">
                <div>{invData.agent_model ?? 'unknown model'}</div>
                {invData.agent_tool_calls != null && <div>{invData.agent_tool_calls} tool calls</div>}
                <div>{new Date(invData.started_at).toLocaleString()}</div>
              </div>
            </div>

            {/* Finding */}
            {invData.finding_text && (
              <div className="mb-5">
                <div className="mb-3 text-xs font-medium text-slate-400">Investigation Finding</div>
                <FindingReport investigation={invData} />
              </div>
            )}

            {/* Review form — only shown if pending */}
            {invData.status === 'pending_review' && !lastResult && (
              <div className="rounded-lg border border-slate-700 bg-slate-900/80 p-4">
                {DEMO_MODE ? (
                  <>
                    <div className="mb-3 rounded border border-amber-700/40 bg-amber-900/20 px-3 py-2 text-xs text-amber-300/70">
                      <AlertCircle className="mb-0.5 inline h-3.5 w-3.5" />{' '}
                      Demo mode — decisions are stored in local browser state only.
                      No server call is made.
                    </div>
                    <div className="mb-4">
                      <label className="mb-1 block text-xs text-slate-500">Notes (optional)</label>
                      <textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        rows={2}
                        placeholder="Add reviewer notes…"
                        className="w-full resize-none rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-amber-500/50 focus:outline-none"
                      />
                    </div>
                    <div className="flex gap-3">
                      <button
                        onClick={() => handleReview('approve')}
                        disabled={reviewMutation.isPending}
                        className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 py-2.5 text-sm font-medium text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50"
                      >
                        <CheckCircle className="h-4 w-4" />
                        Approve (local)
                      </button>
                      <button
                        onClick={() => handleReview('reject')}
                        disabled={reviewMutation.isPending}
                        className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 py-2.5 text-sm font-medium text-red-400 hover:bg-red-500/20 disabled:opacity-50"
                      >
                        <XCircle className="h-4 w-4" />
                        Reject (local)
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="mb-3 flex items-center gap-2 text-xs font-medium text-slate-400">
                      <Lock className="h-3.5 w-3.5" />
                      Human Review — Token Required
                    </div>

                    <div className="mb-3 rounded border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-400">
                      <AlertCircle className="mb-0.5 inline h-3.5 w-3.5" /> The review token is validated
                      server-side. It never appears in source code or browser storage.
                    </div>

                    <div className="mb-3">
                      <label className="mb-1 block text-xs text-slate-500">
                        Human Review Password
                      </label>
                      <div className="relative">
                        <input
                          type={showPassword ? 'text' : 'password'}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="Enter review token…"
                          className="w-full rounded border border-slate-700 bg-slate-800 py-2 pl-3 pr-9 text-sm text-slate-200 focus:border-amber-500/50 focus:outline-none"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(!showPassword)}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400"
                        >
                          {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>

                    <div className="mb-4">
                      <label className="mb-1 block text-xs text-slate-500">Review Notes (optional)</label>
                      <textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        rows={2}
                        placeholder="Add reviewer notes…"
                        className="w-full resize-none rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-amber-500/50 focus:outline-none"
                      />
                    </div>

                    {reviewMutation.error && (
                      <div className="mb-3 flex items-center gap-2 rounded border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-400">
                        <XCircle className="h-3.5 w-3.5" />
                        {(reviewMutation.error as Error).message}
                      </div>
                    )}

                    <div className="flex gap-3">
                      <button
                        onClick={() => handleReview('approve')}
                        disabled={!password || reviewMutation.isPending}
                        className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 py-2.5 text-sm font-medium text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50"
                      >
                        <CheckCircle className="h-4 w-4" />
                        Approve
                      </button>
                      <button
                        onClick={() => handleReview('reject')}
                        disabled={!password || reviewMutation.isPending}
                        className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 py-2.5 text-sm font-medium text-red-400 hover:bg-red-500/20 disabled:opacity-50"
                      >
                        <XCircle className="h-4 w-4" />
                        Reject
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Post-review result */}
            {lastResult && (
              <div
                className={`flex items-center gap-3 rounded-lg border p-4 ${
                  lastResult.action === 'approve'
                    ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400'
                    : 'border-red-500/20 bg-red-500/5 text-red-400'
                }`}
              >
                {lastResult.action === 'approve' ? (
                  <CheckCircle className="h-5 w-5" />
                ) : (
                  <XCircle className="h-5 w-5" />
                )}
                <div>
                  <div className="text-sm font-medium capitalize">
                    Investigation {lastResult.status}
                  </div>
                  <div className="text-xs opacity-70">Review complete</div>
                </div>
              </div>
            )}

            {/* Already reviewed */}
            {invData.status !== 'pending_review' && !lastResult && (
              <div
                className={`rounded-lg border p-4 ${
                  invData.status === 'approved'
                    ? 'border-emerald-500/20 bg-emerald-500/5'
                    : invData.status === 'rejected'
                    ? 'border-red-500/20 bg-red-500/5'
                    : 'border-slate-700 bg-slate-800/50'
                }`}
              >
                <div className="mb-2 text-sm text-slate-400">
                  This investigation has already been reviewed.
                </div>
                <StatusBadge status={invData.status} size="md" />
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}
