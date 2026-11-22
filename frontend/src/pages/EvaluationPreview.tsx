import { BarChart2, FlaskConical, GitBranch, ShieldCheck, AlertCircle } from 'lucide-react'
import { useInvestigations } from '../hooks/useInvestigations'
import { StatusBadge } from '../components/StatusBadge'

const PLANNED_METRICS = [
  {
    id: 'accuracy',
    name: 'Root-Cause Accuracy',
    description: 'Fraction of investigations where the AI-identified root cause matches the ground-truth injected scenario.',
    target: '≥ 70%',
    status: 'planned',
  },
  {
    id: 'tier_precision',
    name: 'Evidence Tier Precision',
    description: 'Agreement between agent-assigned evidence tiers and human-expert labels on the same telemetry.',
    target: '≥ 0.75 Cohen κ',
    status: 'planned',
  },
  {
    id: 'false_positive',
    name: 'False Positive Rate',
    description: 'Percentage of investigations concluding an anomaly when the ground truth is nominal operation.',
    target: '≤ 15%',
    status: 'planned',
  },
  {
    id: 'review_rate',
    name: 'Human Review Rate',
    description: 'Fraction of agent findings that correctly reach pending_review before any human action.',
    target: '100%',
    status: 'enforced',
  },
  {
    id: 'no_confidence',
    name: 'No Percentage Confidence Claims',
    description: 'Findings must not contain percentage confidence or probability claims.',
    target: '0 violations',
    status: 'enforced',
  },
]

const SCENARIO_TYPES = [
  { name: 'Bearing wear — early onset',    asset: 'PUMP-01',     injected: 'Vibration_mm_s spike +2σ',          n: 10 },
  { name: 'Flow restriction — partial',    asset: 'PUMP-01',     injected: 'FlowRate_Lmin drop + Pressure_bar up', n: 10 },
  { name: 'Thermal runaway — gradual',     asset: 'MOTOR-01',    injected: 'Temperature_degC trending +0.5°C/hr', n: 10 },
  { name: 'Sensor drift — calibration',    asset: 'CONVEYOR-01', injected: 'Speed_mps constant offset',           n: 5 },
  { name: 'Fill station overfill',         asset: 'FILL-01',     injected: 'Level_pct threshold breach',          n: 5 },
  { name: 'Nominal — no fault',            asset: 'All',         injected: 'None',                                n: 10 },
]

export function EvaluationPreview() {
  const { data: invData } = useInvestigations()

  const approvedCount = invData?.investigations.filter((i) => i.status === 'approved').length ?? 0
  const rejectedCount = invData?.investigations.filter((i) => i.status === 'rejected').length ?? 0
  const failedCount = invData?.investigations.filter((i) => i.status === 'failed').length ?? 0
  const totalCount = invData?.count ?? 0

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Reliability Evaluation</h1>
        <p className="mt-1 text-sm text-slate-500">
          Planned for Milestone 5 · Current session statistics below
        </p>
      </div>

      {/* Honest empty state notice */}
      <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
        <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400" />
        <div className="text-sm text-amber-200/80">
          <span className="font-medium text-amber-300">M5 evaluation not yet run.</span> The metrics
          below are planned targets. Ground-truth scenario injection and batch evaluation will be
          implemented in Milestone 5. All numbers on this page are design specifications, not
          measured results.
        </div>
      </div>

      {/* Current session stats */}
      <div className="mb-6">
        <h2 className="mb-3 text-sm font-medium text-slate-400">Current Session</h2>
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Total Investigations', value: totalCount, color: 'text-slate-200' },
            { label: 'Approved', value: approvedCount, color: 'text-emerald-400' },
            { label: 'Rejected', value: rejectedCount, color: 'text-red-400' },
            { label: 'Failed', value: failedCount, color: 'text-red-500' },
          ].map((stat) => (
            <div key={stat.label} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <div className={`text-2xl font-semibold ${stat.color}`}>{stat.value}</div>
              <div className="mt-0.5 text-xs text-slate-500">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Planned metrics */}
      <div className="mb-6">
        <div className="mb-3 flex items-center gap-2">
          <BarChart2 className="h-4 w-4 text-slate-500" />
          <h2 className="text-sm font-medium text-slate-400">Planned Evaluation Metrics</h2>
        </div>
        <div className="space-y-2">
          {PLANNED_METRICS.map((m) => (
            <div
              key={m.id}
              className="flex items-start gap-4 rounded-lg border border-slate-800 bg-slate-900 p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">{m.name}</span>
                  {m.status === 'enforced' ? (
                    <span className="inline-flex items-center gap-1 rounded border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-xs text-emerald-400">
                      <ShieldCheck className="h-3 w-3" />
                      Enforced
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded border border-blue-500/20 bg-blue-500/10 px-1.5 py-0.5 text-xs text-blue-400">
                      <FlaskConical className="h-3 w-3" />
                      Planned
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-xs text-slate-500">{m.description}</div>
              </div>
              <div className="flex-shrink-0 text-right">
                <div className="text-xs text-slate-400">Target</div>
                <div className="font-mono text-sm text-amber-400">{m.target}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Planned scenarios */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-slate-500" />
          <h2 className="text-sm font-medium text-slate-400">Planned Test Scenarios (M5)</h2>
        </div>
        <div className="rounded-lg border border-slate-800">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-500">
                <th className="px-4 py-2 text-left font-medium">Scenario</th>
                <th className="px-4 py-2 text-left font-medium">Asset</th>
                <th className="px-4 py-2 text-left font-medium">Injected Signal</th>
                <th className="px-4 py-2 text-right font-medium">N</th>
                <th className="px-4 py-2 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {SCENARIO_TYPES.map((s) => (
                <tr key={s.name} className="bg-slate-900 hover:bg-slate-800/50">
                  <td className="px-4 py-2.5 font-medium text-slate-300">{s.name}</td>
                  <td className="px-4 py-2.5 font-mono text-amber-400">{s.asset}</td>
                  <td className="px-4 py-2.5 text-slate-500">{s.injected}</td>
                  <td className="px-4 py-2.5 text-right text-slate-400">{s.n}</td>
                  <td className="px-4 py-2.5 text-right">
                    <StatusBadge status="UNKNOWN" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 text-xs text-slate-600">
          Total planned: {SCENARIO_TYPES.reduce((a, s) => a + s.n, 0)} scenarios · 0 executed
        </div>
      </div>
    </div>
  )
}
