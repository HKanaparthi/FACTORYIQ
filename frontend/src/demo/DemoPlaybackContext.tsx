import React, { createContext, useContext, useEffect, useRef, useState } from 'react'
import { DEMO_PLAYBACK_MAX_INDEX } from './fixtures/telemetry'

interface PlaybackContextValue {
  playbackIndex: number
  playing: boolean
  play: () => void
  pause: () => void
  restart: () => void
}

const DemoPlaybackContext = createContext<PlaybackContextValue>({
  playbackIndex: DEMO_PLAYBACK_MAX_INDEX - 1,
  playing: false,
  play: () => {},
  pause: () => {},
  restart: () => {},
})

export function DemoPlaybackProvider({ children }: { children: React.ReactNode }) {
  const [playbackIndex, setPlaybackIndex] = useState(0)
  const [playing, setPlaying] = useState(true)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!playing) {
      if (intervalRef.current) clearInterval(intervalRef.current)
      return
    }
    intervalRef.current = setInterval(() => {
      setPlaybackIndex(prev => {
        if (prev >= DEMO_PLAYBACK_MAX_INDEX - 1) {
          setPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, 2000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [playing])

  const play = () => setPlaying(true)
  const pause = () => setPlaying(false)
  const restart = () => { setPlaybackIndex(0); setPlaying(true) }

  return (
    <DemoPlaybackContext.Provider value={{ playbackIndex, playing, play, pause, restart }}>
      {children}
    </DemoPlaybackContext.Provider>
  )
}

export function useDemoPlayback() {
  return useContext(DemoPlaybackContext)
}
