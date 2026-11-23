import { useState } from 'react'
import {
  BarChart2,
  CheckCircle2,
  XCircle,
  HelpCircle,
  AlertTriangle,
  Play,
  Loader2,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  GitBranch,
  ShieldCheck,
  Info,
} from 'lucide-react'
import {
  useScenarios,
  useEvalRuns,
  useEvalRun,
  useEvalResults,
  useStartRun,
  useFourConditions,
} from '../hooks/useEval'
import type { DiagnosticVerdict, EvalResult, EvalScenario, EvalRunStatus } from '../api/types'
import { DEMO_MODE } from '../demo'
import { DEMO_EVAL_RUN } from '../demo/fixtures/evalRuns'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const VERDICT_META: Record<
  DiagnosticVerdict,
  { label: string; color: string; icon: React.ReactNode }
> = {
  correct: {
    label: 'Correct',
    color: 'text-emerald-400',
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
  },
  incorrect: {
    label: 'Incorrect',
    color: 'text-red-400',
    icon: <XCircle className="h-3.5 w-3.5" />,
  },
  acceptable_alt: {
    label: 'Acceptable Alt',
    color: 'text-amber-400',
    icon: <AlertTriangle className="h-3.5 w-3.5" />,
  },
  uncertain_correct: {
    label: 'Uncertain Correct',
    color: 'text-sky-400',
    icon: <HelpCircle className="h-3.5 w-3.5" />,
  },
  non_evaluable: {
    label: 'Non-Evaluable',
    color: 'text-slate-500',
    icon: <HelpCircle className="h-3.5 w-3.5" />,
  },
}

const CATEGORY_LABEL: Record<string, string> = {
  equipment_fault: 'Equipment Fault',
  evidence_quality: 'Evidence Quality',
  connectivity: 'Connectivity',
  investigation_failure: 'Investigation Failure',
  safety_ambiguity: 'Safety / Ambiguity',
  four_condition: 'Four Conditions',
}

const STATUS_COLOR: Record<EvalRunStatus, string> = {
  pending: 'text-slate-400',
  running: 'text-amber-400',
  completed: 'text-emerald-400',
  failed: 'text-red-400',
  cancelled: 'text-slate-500',
}

function VerdictBadge({ verdict }: { verdict: DiagnosticVerdict | null }) {
  if (!verdict) return <span className="text-slate-600 text-xs">—</span>
  const m = VERDICT_META[verdict]
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${m.color}`}>
      {m.icon}
      {m.label}
    </span>
  )
}

function BoolDot({ val }: { val: boolean | null }) {
  if (val === null) return <span className="text-slate-600">—</span>
  return val ? (
    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
  ) : (
    <XCircle className="h-3.5 w-3.5 text-red-400" />
  )
}

// ---------------------------------------------------------------------------
// Scenario List Panel
// ---------------------------------------------------------------------------

function ScenarioList({ scenarios }: { scenarios: EvalScenario[] }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const byCategory = scenarios.reduce<Record<string, EvalScenario[]>>((acc, s) => {
    ;(acc[s.category] ??= []).push(s)
    return acc
  }, {})

  return (
    <div className="space-y-3">
      {Object.entries(byCategory).map(([cat, items]) => (
        <div key={cat} className="rounded-lg border border-slate-800">
          <div className="border-b border-slate-800 px-4 py-2">
            <span className="text-xs font-medium text-slate-400">
              {CATEGORY_LABEL[cat] ?? cat}
            </span>
            <span className="ml-2 text-xs text-slate-600">({items.length})</span>
          </div>
          <div className="divide-y divide-slate-800/50">
            {items.map((s) => (
              <div key={s.scenario_id}>
                <button
                  onClick={() =>
                    setExpanded((p) => (p === s.scenario_id ? null : s.scenario_id))
                  }
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-slate-800/40"
                >
                  {expanded === s.scenario_id ? (
                    <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 text-slate-500" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-slate-500" />
                  )}
                  <span className="font-mono text-xs text-amber-400">{s.scenario_id}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-slate-300">{s.name}</span>
                  <span className="flex-shrink-0 rounded border border-slate-700 px-1.5 py-0.5 font-mono text-xs text-slate-500">
                    {s.evidence_condition}
                  </span>
                </button>
                {expanded === s.scenario_id && (
                  <div className="border-t border-slate-800/50 bg-slate-900/50 px-4 py-3 text-xs text-slate-400">
                    <p className="mb-2 leading-relaxed">{s.description}</p>
                    <div className="flex gap-4 text-slate-500">
                      <span>Asset: <span className="font-mono text-amber-500">{s.asset_id}</span></span>
                      <span>Version: {s.version}</span>
                      <span>Seed: {s.seed}</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run Results Panel
// ---------------------------------------------------------------------------

function RunResultsPanel({ runId }: { runId: string }) {
  const { data: run } = useEvalRun(runId)
  const { data: results } = useEvalResults(runId)

  if (!run) return <div className="text-xs text-slate-500">Loading run…</div>

  const summary = run.summary
  const totalEval = (summary?.correct ?? 0) +
    (summary?.incorrect ?? 0) +
    (summary?.acceptable_alt ?? 0) +
    (summary?.uncertain_correct ?? 0)
  const evaluable = totalEval + (summary?.non_evaluable ?? 0)
  const pct = evaluable > 0 ? Math.round((((summary?.correct ?? 0) + (summary?.uncertain_correct ?? 0)) / evaluable) * 100) : null

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <span className="font-mono text-xs text-slate-500">Run </span>
          <span className="font-mono text-xs text-slate-300">{runId.slice(0, 8)}…</span>
        </div>
        <span className={`text-xs font-medium ${STATUS_COLOR[run.status as EvalRunStatus]}`}>
          {run.status}
          {run.status === 'running' && (
            <Loader2 className="ml-1 inline h-3 w-3 animate-spin" />
          )}
        </span>
      </div>

      {/* Progress bar */}
      {run.total_scenarios && (
        <div>
          <div className="mb-1 flex justify-between text-xs text-slate-500">
            <span>Progress</span>
            <span>{run.completed_scenarios}/{run.total_scenarios}</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-slate-800">
            <div
              className="h-1.5 rounded-full bg-amber-500 transition-all"
              style={{
                width: `${(run.completed_scenarios / run.total_scenarios) * 100}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Summary verdict counts */}
      {summary && (
        <div className="grid grid-cols-5 gap-2">
          {(
            [
              ['correct', 'Correct', 'text-emerald-400'],
              ['incorrect', 'Incorrect', 'text-red-400'],
              ['acceptable_alt', 'Alt', 'text-amber-400'],
              ['uncertain_correct', 'Uncertain OK', 'text-sky-400'],
              ['non_evaluable', 'N/E', 'text-slate-500'],
            ] as const
          ).map(([key, label, color]) => (
            <div key={key} className="rounded-lg border border-slate-800 bg-slate-900 p-2 text-center">
              <div className={`text-lg font-semibold ${color}`}>
                {(summary as unknown as Record<string, number>)[key] ?? 0}
              </div>
              <div className="text-xs text-slate-600">{label}</div>
            </div>
          ))}
        </div>
      )}

      {pct !== null && (
        <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-3 text-center">
          <div className="text-2xl font-bold text-slate-200">{pct}%</div>
          <div className="text-xs text-slate-500">correct + uncertain_correct / evaluable</div>
          <div className="mt-1 rounded border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-xs text-amber-300/70">
            Scripted runner only — not Claude model accuracy
          </div>
        </div>
      )}

      {/* Per-scenario rows */}
      {results && results.length > 0 && (
        <div className="rounded-lg border border-slate-800">
          <div className="border-b border-slate-800 px-4 py-2 text-xs font-medium text-slate-500">
            Per-scenario results
          </div>
          <div className="divide-y divide-slate-800/50">
            {results.map((r) => (
              <ResultRow key={r.run_scenario_id} result={r} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ResultRow({ result }: { result: EvalResult }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button
        onClick={() => setOpen((p) => !p)}
        className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-800/40"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 text-slate-500" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-slate-500" />
        )}
        <span className="w-16 font-mono text-xs text-amber-400">{result.scenario_id}</span>
        <span className="min-w-0 flex-1 text-left">
          <VerdictBadge verdict={result.diagnostic_verdict} />
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <BoolDot val={result.completed} />
          <BoolDot val={result.evidence_grounded} />
          <BoolDot val={result.tool_use_ok} />
        </span>
      </button>
      {open && (
        <div className="border-t border-slate-800/50 bg-slate-900/50 px-4 py-3 text-xs text-slate-400">
          {result.failure_reason && (
            <p className="mb-2 text-red-400">{result.failure_reason}</p>
          )}
          {result.investigation_id && (
            <p className="mb-1">
              Investigation:{' '}
              <a
                href={`/evidence?investigation=${result.investigation_id}`}
                className="font-mono text-sky-400 hover:underline"
              >
                {result.investigation_id.slice(0, 8)}…
              </a>
            </p>
          )}
          <div className="mt-2 grid grid-cols-3 gap-2 text-slate-500">
            <span>Completed: <BoolDot val={result.completed} /></span>
            <span>Grounded: <BoolDot val={result.evidence_grounded} /></span>
            <span>Tool use OK: <BoolDot val={result.tool_use_ok} /></span>
            <span>Uncertainty: <BoolDot val={result.uncertainty_handled} /></span>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Four-Condition Panel
// ---------------------------------------------------------------------------

const CONDITION_LABELS: Record<string, { letter: string; label: string; color: string }> = {
  'FC-001': { letter: 'A', label: 'Fresh Data', color: 'text-emerald-400' },
  'FC-002': { letter: 'B', label: 'Stale Sensor', color: 'text-amber-400' },
  'FC-003': { letter: 'C', label: 'Contradictory', color: 'text-orange-400' },
  'FC-004': { letter: 'D', label: 'Wrong Asset', color: 'text-red-400' },
}

function FourConditionsPanel() {
  const { data, isLoading } = useFourConditions()
  if (isLoading) return <div className="text-xs text-slate-500">Loading…</div>
  if (!data) return null

  return (
    <div className="space-y-3">
      <div className="text-xs text-slate-500">
        Same PUMP-01 pressure scenario under four evidence conditions.
        Demonstrates how data quality affects investigation conclusions.
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {data.scenarios.map((s) => {
          const meta = CONDITION_LABELS[s.scenario_id]
          const result = data.latest_results[s.scenario_id]
          return (
            <div
              key={s.scenario_id}
              className="rounded-lg border border-slate-800 bg-slate-900 p-4"
            >
              <div className="mb-2 flex items-center gap-2">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full border border-current text-xs font-bold ${meta?.color ?? 'text-slate-400'}`}
                >
                  {meta?.letter ?? '?'}
                </span>
                <span className="text-sm font-medium text-slate-200">{meta?.label ?? s.scenario_id}</span>
                <span className="ml-auto font-mono text-xs text-slate-600">{s.scenario_id}</span>
              </div>
              <p className="mb-3 text-xs leading-relaxed text-slate-500">{s.description}</p>
              <div className="flex items-center gap-2 border-t border-slate-800 pt-2">
                <span className="text-xs text-slate-600">Latest result:</span>
                {result ? (
                  <VerdictBadge verdict={result.diagnostic_verdict} />
                ) : (
                  <span className="text-xs text-slate-600">No run yet</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run History Panel
// ---------------------------------------------------------------------------

function RunHistory({ onSelect }: { onSelect: (id: string) => void }) {
  const { data: runs } = useEvalRuns()
  if (!runs || runs.length === 0) {
    return <div className="text-xs text-slate-600">No runs yet.</div>
  }
  return (
    <div className="space-y-2">
      {runs.map((r) => (
        <button
          key={r.run_id}
          onClick={() => onSelect(r.run_id)}
          className="flex w-full items-center gap-3 rounded-lg border border-slate-800 bg-slate-900 px-4 py-2.5 text-left hover:border-slate-700"
        >
          <span className={`text-xs font-medium ${STATUS_COLOR[r.status]}`}>{r.status}</span>
          <span className="font-mono text-xs text-slate-500">{r.run_id.slice(0, 8)}…</span>
          <span className="min-w-0 flex-1 text-xs text-slate-400">
            {r.total_scenarios ?? '?'} scenarios · {r.adapter_type}
          </span>
          <span className="text-xs text-slate-600">
            {r.started_at ? new Date(r.started_at).toLocaleTimeString() : '—'}
          </span>
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type Tab = 'run' | 'scenarios' | 'four-conditions' | 'history'

export function EvaluationWorkspace() {
  const [tab, setTab] = useState<Tab>('run')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    DEMO_MODE ? DEMO_EVAL_RUN.run_id : null,
  )
  const [scenarioFilter, setScenarioFilter] = useState<string | null>(null)

  const { data: scenarios } = useScenarios()
  const startRun = useStartRun()

  const handleStartRun = async (scenarioIds: string[] | null) => {
    try {
      const res = await startRun.mutateAsync({
        scenario_ids: scenarioIds,
        trial_count: 1,
        adapter_type: 'scripted',
      })
      setSelectedRunId(res.run_id)
      setTab('run')
    } catch {
      // error shown inline
    }
  }

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'run', label: 'Run / Results', icon: <BarChart2 className="h-4 w-4" /> },
    { id: 'scenarios', label: 'Scenarios', icon: <GitBranch className="h-4 w-4" /> },
    { id: 'four-conditions', label: 'Four Conditions', icon: <FlaskConical className="h-4 w-4" /> },
    { id: 'history', label: 'History', icon: <ShieldCheck className="h-4 w-4" /> },
  ]

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-slate-100">Reliability Evaluation</h1>
        <p className="mt-1 text-sm text-slate-500">
          Industrial AI evaluation harness · 36 versioned scenarios · scripted adapter only
        </p>
      </div>

      {/* Limitation notice */}
      <div className="mb-5 flex items-start gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
        <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-400" />
        <div className="text-xs text-amber-200/70">
          <span className="font-medium text-amber-300">Scripted runner only.</span> Results reflect
          deterministic rule-based logic, not Claude model accuracy. Pattern matching ≠ semantic
          verification. All <span className="font-mono">non_evaluable</span> and{' '}
          <span className="font-mono">acceptable_alt</span> verdicts require human review.
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-5 flex gap-1 border-b border-slate-800">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm transition-colors ${
              tab === t.id
                ? 'border-amber-500 text-amber-400'
                : 'border-transparent text-slate-500 hover:text-slate-300'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: Run / Results */}
      {tab === 'run' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Left: controls */}
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-800 p-4">
              <h2 className="mb-3 text-sm font-medium text-slate-300">Start Benchmark Run</h2>

              <div className="mb-3">
                <label className="mb-1 block text-xs text-slate-500">Scope</label>
                <select
                  className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-300"
                  value={scenarioFilter ?? 'all'}
                  onChange={(e) =>
                    setScenarioFilter(e.target.value === 'all' ? null : e.target.value)
                  }
                >
                  <option value="all">All 36 scenarios</option>
                  <option value="equipment_fault">Equipment Fault (8)</option>
                  <option value="evidence_quality">Evidence Quality (10)</option>
                  <option value="connectivity">Connectivity (5)</option>
                  <option value="investigation_failure">Investigation Failure (5)</option>
                  <option value="safety_ambiguity">Safety / Ambiguity (4)</option>
                  <option value="four_condition">Four Conditions (4)</option>
                </select>
              </div>

              {DEMO_MODE ? (
                <div className="rounded border border-amber-700/40 bg-amber-900/20 px-3 py-2 text-xs text-amber-300/70">
                  Recorded Benchmark Results — Run disabled in demo mode.
                  Results below are from a pre-recorded scripted adapter run.
                </div>
              ) : (
                <>
                  <button
                    onClick={() => {
                      const ids =
                        scenarioFilter && scenarios
                          ? scenarios
                              .filter((s) => s.category === scenarioFilter)
                              .map((s) => s.scenario_id)
                          : null
                      handleStartRun(ids)
                    }}
                    disabled={startRun.isPending}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-500 disabled:opacity-50"
                  >
                    {startRun.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                    Run Benchmark
                  </button>

                  {startRun.isError && (
                    <p className="mt-2 text-xs text-red-400">{startRun.error?.message}</p>
                  )}
                </>
              )}
            </div>

            {/* Recent runs */}
            <div>
              <h2 className="mb-2 text-sm font-medium text-slate-400">Recent Runs</h2>
              <RunHistory
                onSelect={(id) => {
                  setSelectedRunId(id)
                }}
              />
            </div>
          </div>

          {/* Right: results */}
          <div className="lg:col-span-2">
            {selectedRunId ? (
              <RunResultsPanel runId={selectedRunId} />
            ) : (
              <div className="flex h-48 items-center justify-center rounded-lg border border-slate-800 text-sm text-slate-600">
                Start a run or select one from history to see results
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab: Scenarios */}
      {tab === 'scenarios' && (
        <div>
          <div className="mb-3 text-xs text-slate-500">
            {scenarios?.length ?? 0} scenarios · ground truth is not shown here
          </div>
          {scenarios ? (
            <ScenarioList scenarios={scenarios} />
          ) : (
            <div className="text-xs text-slate-600">Loading scenarios…</div>
          )}
        </div>
      )}

      {/* Tab: Four Conditions */}
      {tab === 'four-conditions' && <FourConditionsPanel />}

      {/* Tab: History */}
      {tab === 'history' && (
        <div>
          <RunHistory
            onSelect={(id) => {
              setSelectedRunId(id)
              setTab('run')
            }}
          />
        </div>
      )}
    </div>
  )
}
