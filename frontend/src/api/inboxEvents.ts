/** Personal inbox events (new DM, @mention, bell notification) from the live socket — the
 * source of desktop notifications. See backend apps/notifications/inbox.py. */
export interface InboxEvent {
  id: string
  kind: 'message' | 'notification'
  /** Same for every event about one chat message, so they collapse into one notification. */
  tag: string
  title: string
  body: string
  /** In-app path to open on click. */
  url: string
  channel_id: number | null
  created_at: string
}

type Listener = (event: InboxEvent) => void

const listeners = new Set<Listener>()
let liveConnected = false

export function onInboxEvent(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function emitInboxEvent(event: InboxEvent) {
  for (const listener of listeners) listener(event)
}

/** Whether the live socket is up; when it isn't, inbox events are polled instead. */
export function setLiveConnected(connected: boolean) {
  liveConnected = connected
}

export function isLiveConnected(): boolean {
  return liveConnected
}
