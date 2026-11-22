import { useState } from 'react'
import {
  Lightbulb,
  ShieldAlert,
  GitBranch,
  AlertTriangle,
  CheckSquare,
  Info,
  ChevronDown,
  ChevronRight,
  Terminal,
} from 'lucide-react'
import type { Investigation } from '../api/types'
import { StatusBadge } from './StatusBadge'
import { TierBadge } from './TierBadge'

// ---------------------------------------------------------------------------
// Known section headers in the scripted finding template
// ---------------------------------------------------------------------------

interface ParsedFinding {
  isScripted: boolean
  hypothesis: string
  supporting: Array<{ text: string; tier: string | null }>
  alternatives: string[]
  caveats: string[]
  nextActions: string[]
  notice: string
  raw: string
}

function parseFinding(text: string): ParsedFinding {
  const isScripted = text.includes('[SCRIPTED DEMONSTRATION]')

  const sections: Record<string, string[]> = {
    hypothesis: [],
    supporting: [],
    alternatives: [],
    caveats: [],
    nextActions: [],
    notice: [],
  }

  const SECTION_MAP: Record<string, keyof typeof sections> = {
    'HYPOTHESIS:':                'hypothesis',
    'SUPPORTING EVIDENCE:':       'supporting',
    'ALTERNATIVE HYPOTHESES:':    'alternatives',
    'DATA QUALITY CAVEATS:':      'caveats',
    'RECOMMENDED NEXT ACTION:':   'nextActions',
    'SIMULATED DATA NOTICE:':     'notice',
  }

  let current: keyof typeof sections | null = null

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim()
    if (!line || line === '[SCRIPTED DEMONSTRATION]') continue

    // Check for the scripted-runner notice lines
    if (line.startsWith('This finding was generated') || line.startsWith('Observations are derived')) continue

    // Section header detection
    let matched = false
    for (const [header, key] of Object.entries(SECTION_MAP)) {
      if (line.startsWith(header)) {
        current = key
        const rest = line.slice(header.length).trim()
        if (rest) sections[key].push(rest)
        matched = true
        break
      }
    }
    if (matched) continue

    if (current) {
      sections[current].push(line)
    }
  }

  // Parse supporting evidence items: "text: TIER_LABEL"
  const supporting = sections.supporting
    .filter((l) => l.startsWith('-'))
    .map((l) => {
      const content = l.replace(/^-\s*/, '').trim()
      const tierPattern = /:\s*(CONFIRMED_OBSERVATION|STATISTICAL_SIGNAL|CORROBORATING_EVIDENCE|WEAK_SIGNAL|INSUFFICIENT_DATA)\s*$/
      const match = content.match(tierPattern)
      if (match) {
        return { text: content.slice(0, match.index).trim(), tier: match[1] }
      }
      return { text: content, tier: null }
    })

  const listify = (key: keyof typeof sections) =>
    sections[key]
      .filter((l) => l.startsWith('-'))
      .map((l) => l.replace(/^-\s*/, '').trim())

  return {
    isScripted,
    hypothesis: sections.hypothesis.join(' ').trim(),
    supporting: supporting.length ? supporting : [],
    alternatives: listify('alternatives'),
    caveats: listify('caveats'),
    nextActions: listify('nextActions'),
    notice: sections.notice.join(' ').trim(),
    raw: text,
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Section({
  icon: Icon,
  title,
  children,
  color = 'text-slate-400',
}: {
  icon: React.ElementType
  title: string
  children: React.ReactNode
  color?: string
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <div className={`mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide ${color}`}>
        <Icon className="h-3.5 w-3.5 flex-shrink-0" />
        {title}
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  investigation: Investigation
  compact?: boolean
}

export function FindingReport({ investigation, compact = false }: Props) {
  const [showRaw, setShowRaw] = useState(false)

  const finding = investigation.finding_text
  if (!finding) {
    return (
      <div className="rounded-lg border border-dashed border-slate-800 px-4 py-8 text-center text-sm text-slate-600">
        No finding available
      </div>
    )
  }

  const parsed = parseFinding(finding)
  const hasStructure = parsed.hypothesis || parsed.supporting.length > 0

  return (
    <div className="space-y-3">
      {/* Header badges */}
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={investigation.status} size="md" />
        {parsed.isScripted && (
          <span className="inline-flex items-center gap-1 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400">
            <Terminal className="h-3 w-3" />
            Scripted Demo · Rule-based, not AI
          </span>
        )}
        {investigation.agent_model && (
          <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-500">
            {investigation.agent_model}
          </span>
        )}
        {investigation.agent_tool_calls && (
          <span className="text-xs text-slate-600">{investigation.agent_tool_calls} tool calls</span>
        )}
      </div>

      {hasStructure ? (
        <div className="space-y-3">
          {/* Hypothesis */}
          {parsed.hypothesis && (
            <Section icon={Lightbulb} title="Primary Hypothesis" color="text-amber-400">
              <p className="text-sm leading-relaxed text-slate-300">{parsed.hypothesis}</p>
            </Section>
          )}

          {/* Supporting Evidence */}
          {parsed.supporting.length > 0 && (
            <Section icon={ShieldAlert} title="Supporting Observations" color="text-blue-400">
              <div className="space-y-2">
                {parsed.supporting.map((item, i) => {
                  const evidenceItem = investigation.evidence_items[i]
                  return (
                    <div key={i} className="flex items-start gap-2">
                      <span className="mt-0.5 text-slate-600">•</span>
                      <div className="min-w-0 flex-1">
                        <span className="text-sm text-slate-300">{item.text}</span>
                        {item.tier && (
                          <TierBadge tier={item.tier} compact className="ml-2" />
                        )}
                        {evidenceItem && (
                          <div className="mt-0.5 text-xs text-slate-600">
                            Evidence #{evidenceItem.sequence_num} · {evidenceItem.tool_name} ·{' '}
                            {new Date(evidenceItem.recorded_at).toLocaleTimeString()}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </Section>
          )}

          {/* Alternative Hypotheses */}
          {parsed.alternatives.length > 0 && (
            <Section icon={GitBranch} title="Alternative Hypotheses" color="text-violet-400">
              <ul className="space-y-1">
                {parsed.alternatives.map((alt, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-400">
                    <span className="mt-0.5 text-slate-600">•</span>
                    <span>{alt}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Caveats + Next Actions in a row (unless compact) */}
          {!compact && (
            <div className="grid grid-cols-2 gap-3">
              {parsed.caveats.length > 0 && (
                <Section icon={AlertTriangle} title="Data Quality Caveats" color="text-amber-400">
                  <ul className="space-y-1">
                    {parsed.caveats.map((c, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                        <span className="mt-0.5 text-slate-600">•</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
              {parsed.nextActions.length > 0 && (
                <Section icon={CheckSquare} title="Recommended Actions" color="text-emerald-400">
                  <ul className="space-y-1">
                    {parsed.nextActions.map((a, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                        <span className="mt-0.5 text-emerald-600">→</span>
                        <span>{a}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>
          )}

          {/* Simulated notice */}
          {(parsed.notice || parsed.isScripted) && (
            <div className="flex items-start gap-2 rounded border border-slate-700/50 bg-slate-800/30 px-3 py-2">
              <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-slate-500" />
              <p className="text-xs text-slate-500">
                {parsed.notice ||
                  'This investigation used simulated equipment data. All findings require human verification before operational action.'}
              </p>
            </div>
          )}

          {/* Raw text toggle */}
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="flex items-center gap-1 text-xs text-slate-600 hover:text-slate-400"
          >
            {showRaw ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {showRaw ? 'Hide' : 'Show'} raw finding text
          </button>
          {showRaw && (
            <pre className="rounded-lg border border-slate-800 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-500 whitespace-pre-wrap">
              {finding}
            </pre>
          )}
        </div>
      ) : (
        // Fallback: unstructured text display
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-300">
            {finding}
          </pre>
        </div>
      )}
    </div>
  )
}
