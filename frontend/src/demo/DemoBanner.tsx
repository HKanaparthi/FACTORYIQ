import { useDemoPlayback } from './DemoPlaybackContext'
import { DEMO_PLAYBACK_MAX_INDEX } from './fixtures/telemetry'

export function DemoBanner() {
  const { playbackIndex, playing, play, pause, restart } = useDemoPlayback()
  const pct = Math.round((playbackIndex / (DEMO_PLAYBACK_MAX_INDEX - 1)) * 100)

  return (
    <div className="bg-amber-900/80 border-b border-amber-700 text-amber-100 text-xs px-4 py-1.5 flex items-center gap-4 select-none">
      <span className="font-semibold tracking-wide uppercase text-amber-300">Demo Mode</span>
      <span className="opacity-75">Recorded Simulation — No live backend or AI inference</span>

      <div className="ml-auto flex items-center gap-3">
        <span className="opacity-60">Telemetry playback</span>
        <div className="w-28 h-1.5 bg-amber-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-amber-400 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="tabular-nums w-7 text-right opacity-75">{pct}%</span>

        {playing ? (
          <button
            onClick={pause}
            className="px-2 py-0.5 rounded bg-amber-700 hover:bg-amber-600 text-amber-100 font-mono text-xs"
            aria-label="Pause playback"
          >
            ⏸
          </button>
        ) : (
          <button
            onClick={play}
            className="px-2 py-0.5 rounded bg-amber-700 hover:bg-amber-600 text-amber-100 font-mono text-xs"
            aria-label="Resume playback"
          >
            ▶
          </button>
        )}
        <button
          onClick={restart}
          className="px-2 py-0.5 rounded bg-amber-700 hover:bg-amber-600 text-amber-100 font-mono text-xs"
          aria-label="Restart playback"
        >
          ↺
        </button>
      </div>
    </div>
  )
}
