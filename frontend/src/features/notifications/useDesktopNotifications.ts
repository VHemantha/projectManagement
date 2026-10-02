import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { desktopPermission, shouldNotify, showDesktopNotification } from './desktopNotifications'
import { apiClient } from '@/api/client'
import { type InboxEvent, isLiveConnected, onInboxEvent } from '@/api/inboxEvents'
import { useAuthStore } from '@/store/authStore'

/** How often to check for inbox events while the live socket is down. */
const POLL_MS = 30_000

/** Mounted once (AppShell): turns inbox events — pushed over the live socket, or polled while
 * it is down — into desktop notifications. */
export function useDesktopNotifications() {
  const enabled = useAuthStore((s) => s.user?.desktop_notifications ?? true)
  const loggedIn = useAuthStore((s) => !!s.accessToken)
  const navigate = useNavigate()

  useEffect(() => {
    if (!loggedIn || !enabled) return undefined
    const seen = new Set<string>()

    const handle = (event: InboxEvent) => {
      if (seen.has(event.id)) return
      seen.add(event.id)
      const ctx = {
        enabled,
        permission: desktopPermission(),
        focused: document.hasFocus(),
        // Read at the moment the event arrives (the app uses a browser router).
        pathname: window.location.pathname,
      }
      if (shouldNotify(event, ctx)) showDesktopNotification(event, navigate)
    }

    const unsubscribe = onInboxEvent(handle)

    // Polling fallback: only while the socket is down and notifications can actually show.
    let cursor = new Date().toISOString()
    const poll = async () => {
      if (isLiveConnected() || desktopPermission() !== 'granted') {
        cursor = new Date().toISOString()
        return
      }
      try {
        const { data } = await apiClient.get<{ events: InboxEvent[]; now: string }>('/notifications/inbox/', {
          params: { since: cursor },
        })
        cursor = data.now
        data.events.forEach(handle)
      } catch {
        // Offline too; try again next time.
      }
    }
    const timer = setInterval(poll, POLL_MS)

    return () => {
      unsubscribe()
      clearInterval(timer)
    }
  }, [enabled, loggedIn, navigate])
}
