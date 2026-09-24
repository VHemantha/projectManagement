import { type QueryClient, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { useAuthStore } from '@/store/authStore'

const MAX_BACKOFF_MS = 10_000
// Notices arrive in bursts (one per saved row); refetch once per burst.
const FLUSH_DELAY_MS = 300

type LiveKind = 'issues' | 'issue' | 'board' | 'project' | 'sprints' | 'teams' | 'clients'

interface LiveEvent {
  type: 'live.change'
  kind: LiveKind
  project: string | null
  key: string | null
}

function wsUrl(token: string) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/live/?token=${encodeURIComponent(token)}`
}

/** Query keys a batch of change notices makes stale. Invalidation only refetches queries that
 * are currently on screen, so a broad key like ['issues'] is cheap for views that aren't open. */
export function keysToInvalidate(events: LiveEvent[]): { queryKey: unknown[]; exact?: boolean }[] {
  const keys = new Map<string, { queryKey: unknown[]; exact?: boolean }>()
  const add = (queryKey: unknown[], exact = false) => keys.set(JSON.stringify([queryKey, exact]), { queryKey, exact })

  for (const e of events) {
    switch (e.kind) {
      case 'issues':
        add(['issues']) // every board, backlog and issue list
        add(['activity'])
        add(['projects'], true) // issue counts in the projects table
        if (e.key) add(['issue', e.key])
        break
      case 'issue':
        if (e.key) add(['issue', e.key])
        break
      case 'board':
        if (e.project) {
          add(['projects', e.project, 'board']) // columns, colours, statuses, on every board of it
          add(['projects', e.project, 'workflow-transitions'])
        }
        add(['boards'])
        break
      case 'project':
        add(['projects']) // details, labels, task names, boards
        add(['reports', 'nav-tree'])
        break
      case 'sprints':
        if (e.project) add(['sprints', e.project])
        add(['issues']) // completing a sprint moves issues in bulk
        break
      case 'teams':
        add(['teams'])
        add(['reports', 'nav-tree'])
        break
      case 'clients':
        add(['clients'])
        add(['reports', 'nav-tree'])
        break
    }
  }
  return [...keys.values()]
}

const ALL_EVENTS: LiveEvent[] = (['issues', 'project', 'teams', 'clients'] as LiveKind[]).map((kind) => ({
  type: 'live.change',
  kind,
  project: null,
  key: null,
}))

function invalidate(queryClient: QueryClient, events: LiveEvent[]) {
  for (const filter of keysToInvalidate(events)) void queryClient.invalidateQueries(filter)
}

/** Mounted once, app-wide (AppShell). Keeps every open view in step with changes made
 * anywhere — another tab, another user, or another board in this tab — by refetching the data
 * the server says changed. After a dropped connection it refetches everything visible, since
 * notices sent while offline were missed. */
export function useLiveUpdates() {
  const accessToken = useAuthStore((s) => s.accessToken)
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!accessToken) return undefined
    let cancelled = false
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let flushTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0
    let hasConnected = false
    let pending: LiveEvent[] = []

    const flush = () => {
      flushTimer = null
      const batch = pending
      pending = []
      invalidate(queryClient, batch)
    }

    const connect = () => {
      if (cancelled) return
      socket = new WebSocket(wsUrl(accessToken))

      socket.onopen = () => {
        if (hasConnected) invalidate(queryClient, ALL_EVENTS) // catch up on anything missed
        hasConnected = true
        attempt = 0
      }

      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as LiveEvent
        if (event.type !== 'live.change') return
        pending.push(event)
        flushTimer ??= setTimeout(flush, FLUSH_DELAY_MS)
      }

      socket.onclose = () => {
        if (cancelled) return
        const delay = Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS)
        attempt += 1
        reconnectTimer = setTimeout(connect, delay)
      }

      socket.onerror = () => socket?.close()
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (flushTimer) clearTimeout(flushTimer)
      socket?.close()
    }
  }, [accessToken, queryClient])
}
