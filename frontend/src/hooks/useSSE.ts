import { useCallback, useEffect, useRef, useState } from 'react'
import { sseUrl } from '../api/client'
import type { SSEEvent } from '../api/types'
import { DEMO_MODE } from '../demo'
import { demoStore } from '../demo/demoStore'
import { DEMO_SSE_EVENTS, DEMO_SSE_DELAY_MS } from '../demo/fixtures/sseEvents'

export function useSSE(investigationId: string | null) {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [done, setDone] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const connect = useCallback((id: string) => {
    // Clear any existing connection
    if (esRef.current) esRef.current.close()
    if (intervalRef.current) clearInterval(intervalRef.current)

    setEvents([])
    setDone(false)
    setConnected(false)

    if (DEMO_MODE) {
      setConnected(true)
      let idx = 0
      intervalRef.current = setInterval(() => {
        if (idx >= DEMO_SSE_EVENTS.length) {
          if (intervalRef.current) clearInterval(intervalRef.current)
          setConnected(false)
          return
        }
        const event = DEMO_SSE_EVENTS[idx]
        idx++
        if (event.type === 'heartbeat') return
        setEvents(prev => [...prev, event])
        if (event.type === 'done' || event.type === 'complete' || event.type === 'error') {
          if (event.type === 'complete') {
            demoStore.phase = 'pending_review'
          }
          setDone(true)
          setConnected(false)
          if (intervalRef.current) clearInterval(intervalRef.current)
        }
      }, DEMO_SSE_DELAY_MS)
      return
    }

    const es = new EventSource(sseUrl(id))
    esRef.current = es

    es.onopen = () => setConnected(true)

    es.onmessage = (e) => {
      const event: SSEEvent = JSON.parse(e.data)
      if (event.type === 'heartbeat') return
      setEvents((prev) => [...prev, event])
      if (event.type === 'done' || event.type === 'complete' || event.type === 'error') {
        setDone(true)
        es.close()
        setConnected(false)
      }
    }

    es.onerror = () => {
      setConnected(false)
      es.close()
    }
  }, [])

  const disconnect = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    if (intervalRef.current) clearInterval(intervalRef.current)
    setConnected(false)
  }, [])

  useEffect(() => {
    return () => {
      esRef.current?.close()
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  // Suppress unused-param warning for investigationId in demo mode
  void investigationId

  return { events, connected, done, connect, disconnect }
}
