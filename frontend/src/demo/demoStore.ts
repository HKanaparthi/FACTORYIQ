// Module-level mutable demo store. Tracks the lifecycle of the interactive
// investigation created in the InvestigationWorkspace demo flow.
// Shared across hooks via direct module reference (no React context needed).
// Polling hooks read from this store; they re-query on their normal interval.

export type DemoInvPhase = 'idle' | 'in_progress' | 'pending_review' | 'approved' | 'rejected'

// Status overrides for pre-recorded investigations (after demo review action)
const _statusOverrides: Record<string, 'approved' | 'rejected'> = {}
let _phase: DemoInvPhase = 'idle'

export const demoStore = {
  get phase(): DemoInvPhase { return _phase },
  set phase(p: DemoInvPhase) { _phase = p },

  getStatusOverride(id: string): 'approved' | 'rejected' | null {
    return _statusOverrides[id] ?? null
  },
  setStatusOverride(id: string, status: 'approved' | 'rejected') {
    _statusOverrides[id] = status
  },

  reset() {
    _phase = 'idle'
    for (const k of Object.keys(_statusOverrides)) delete _statusOverrides[k]
  },
}
