import type { EvidenceTier } from '../api/types'

const TIER_CONFIG: Record<EvidenceTier, { label: string; classes: string; short: string }> = {
  CONFIRMED_OBSERVATION: {
    label: 'Confirmed Observation',
    short: 'CONFIRMED',
    classes: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  },
  STATISTICAL_SIGNAL: {
    label: 'Statistical Signal',
    short: 'SIGNAL',
    classes: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  },
  CORROBORATING_EVIDENCE: {
    label: 'Corroborating Evidence',
    short: 'CORROBORATE',
    classes: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
  },
  WEAK_SIGNAL: {
    label: 'Weak Signal',
    short: 'WEAK',
    classes: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  },
  INSUFFICIENT_DATA: {
    label: 'Insufficient Data',
    short: 'INSUFF.',
    classes: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  },
}

interface Props {
  tier: EvidenceTier | string
  compact?: boolean
  className?: string
}

export function TierBadge({ tier, compact = false, className = '' }: Props) {
  const cfg = TIER_CONFIG[tier as EvidenceTier] ?? {
    label: tier,
    short: tier,
    classes: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  }
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${cfg.classes} ${className}`}
    >
      {compact ? cfg.short : cfg.label}
    </span>
  )
}
