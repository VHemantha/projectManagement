import { useEffect, useRef } from 'react'

import { usePresenceStore } from '@/store/presenceStore'
import { useAuthStore } from '@/store/authStore'

const MAX_BACKOFF_MS = 10_000

function wsUrl(token: string) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/presence/?token=${encodeURIComponent(token)}`
}

/** Mounted once, app-wide (see AppShell.tsx) — a single always-on socket that reports "is the
 * app open for this user right now" into the shared presence store, driving the online dot
 * wherever avatars appear. Same reconnect-with-backoff shape as useChatSocket, scoped down
 * (no per-channel id, no send) since this isn't a chat feature, just app-wide presence. */
export function usePresenceSocket() {
  const accessToken = useAuthStore((s) => s.accessToken)
  const setSnapshot = usePresenceStore((s) => s.setSnapshot)
  const setOnline = usePresenceStore((s) => s.setOnline)
  const setOffline = usePresenceStore((s) => s.setOffline)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)

  useEffect(() => {
    if (!accessToken) return undefined
    let cancelled = false
    let latestSocket: WebSocket | null = null
    attemptRef.current = 0

    const connect = () => {
      if (cancelled) return
      const socket = new WebSocket(wsUrl(accessToken))
      latestSocket = socket

      socket.onopen = () => {
        attemptRef.current = 0
      }

      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data)
        if (payload.type === 'presence.snapshot') {
          setSnapshot(payload.user_ids)
        } else if (payload.type === 'presence.update') {
          if (payload.online) setOnline(payload.user_id)
          else setOffline(payload.user_id)
        }
      }

      socket.onclose = () => {
        if (cancelled) return
        const delay = Math.min(1000 * 2 ** attemptRef.current, MAX_BACKOFF_MS)
        attemptRef.current += 1
        reconnectTimer.current = setTimeout(connect, delay)
      }

      socket.onerror = () => socket.close()
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      latestSocket?.close()
    }
  }, [accessToken, setSnapshot, setOnline, setOffline])
}
