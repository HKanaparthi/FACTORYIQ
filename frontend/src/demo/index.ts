// Demo mode is enabled when VITE_DEMO_MODE=true at build time.
// All data comes from local fixtures; no backend services are required.
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'

// Capture metadata — documented clearly so viewers know what they're looking at.
export const DEMO_METADATA = {
  captureDate: '2026-11-22',
  note: 'Synthetic fixture data generated from simulator/tag_model.py physics parameters. Backend was offline at demo build time — no live database was available. Telemetry values are computed from nominal operating ranges and fault profiles defined in the simulator tag model.',
  simulatorRef: 'simulator/tag_model.py · app/agent/runner.py scripted runner',
}
