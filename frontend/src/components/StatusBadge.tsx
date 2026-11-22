import type { InvestigationStatus } from '../api/types'

const CONFIG: Record<
  string,
  { label: string; classes: string }
> = {
  in_progress:    { label: 'Running',        classes: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
  pending_review: { label: 'Pending Review', classes: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  approved:       { label: 'Approved',       classes: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
  rejected:       { label: 'Rejected',       classes: 'bg-red-500/10 text-red-400 border-red-500/20' },
  failed:         { label: 'Failed',         classes: 'bg-red-900/20 text-red-500 border-red-800/30' },
  HEALTHY:        { label: 'Healthy',        classes: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
  DEGRADED:       { label: 'Degraded',       classes: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  WARNING:        { label: 'Warning',        classes: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
  UNKNOWN:        { label: 'Unknown',        classes: 'bg-slate-500/10 text-slate-400 border-slate-500/20' },
  FRESH:          { label: 'Fresh',          classes: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
  STALE:          { label: 'Stale',          classes: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  MISSING:        { label: 'Missing',        classes: 'bg-slate-500/10 text-slate-400 border-slate-500/20' },
  LOW:            { label: 'Low',            classes: 'bg-sky-500/10 text-sky-400 border-sky-500/20' },
  MEDIUM:         { label: 'Medium',         classes: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  HIGH:           { label: 'High',           classes: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
  CRITICAL:       { label: 'Critical',       classes: 'bg-red-500/10 text-red-400 border-red-500/20' },
}

interface Props {
  status: InvestigationStatus | string
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, size = 'sm' }: Props) {
  const cfg = CONFIG[status] ?? { label: status, classes: 'bg-slate-500/10 text-slate-400 border-slate-500/20' }
  const px = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1 text-sm'
  return (
    <span className={`inline-flex items-center rounded border font-medium ${px} ${cfg.classes}`}>
      {cfg.label}
    </span>
  )
}
