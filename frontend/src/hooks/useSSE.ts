import { useCallback, useEffect, useRef, useState } from 'react'
import { sseUrl } from '../api/client'
import type { SSEEvent } from '../api/types'

export function useSSE(investigationId: string | null) {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [done, setDone] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  const connect = useCallback((id: string) => {
    if (esRef.current) esRef.current.close()

    setEvents([])
    setDone(false)
    setConnected(false)

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
    setConnected(false)
  }, [])

  useEffect(() => {
    return () => {
      esRef.current?.close()
    }
  }, [])

  return { events, connected, done, connect, disconnect }
}
