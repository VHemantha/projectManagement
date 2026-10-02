import type { InboxEvent } from '@/api/inboxEvents'

/** Browser support and the current permission ('unsupported' where the API doesn't exist). */
export type DesktopPermission = NotificationPermission | 'unsupported'

export function desktopPermission(): DesktopPermission {
  return typeof window !== 'undefined' && 'Notification' in window ? Notification.permission : 'unsupported'
}

export async function requestDesktopPermission(): Promise<DesktopPermission> {
  if (desktopPermission() === 'unsupported') return 'unsupported'
  return Notification.requestPermission()
}

export interface NotifyContext {
  /** The person's own on/off setting. */
  enabled: boolean
  permission: DesktopPermission
  /** The app's window is focused. */
  focused: boolean
  /** Current in-app path, e.g. "/chat". */
  pathname: string
}

/**
 * Whether an inbox event should pop up as a desktop notification:
 * - never when switched off or the browser hasn't allowed it;
 * - always when the app isn't focused (that's what they're for);
 * - when it is focused, only for chat events (DMs, @mentions) while the inbox (Chat) isn't
 *   open — with the inbox open and focused the message is already on screen, and bell items
 *   show in the app's own bell.
 */
export function shouldNotify(event: InboxEvent, ctx: NotifyContext): boolean {
  if (!ctx.enabled || ctx.permission !== 'granted') return false
  if (!ctx.focused) return true
  return event.channel_id != null && !ctx.pathname.startsWith('/chat')
}

/** Show the OS notification; clicking it focuses the app and opens the message or job. */
export function showDesktopNotification(event: InboxEvent, open: (url: string) => void): Notification {
  const notification = new Notification(event.title, { body: event.body, tag: event.tag, icon: '/favicon.svg' })
  notification.onclick = () => {
    window.focus()
    open(event.url)
    notification.close()
  }
  return notification
}

const JUST_LOGGED_IN = 'tf-just-logged-in'
const PROMPT_DISMISSED = 'tf-desktop-prompt-dismissed'

/** Set at login: the moment we may offer desktop notifications (never on a plain page load). */
export function markJustLoggedIn() {
  try {
    sessionStorage.setItem(JUST_LOGGED_IN, '1')
  } catch {
    // Storage blocked: the offer stays available in Profile.
  }
}

/** Offer to turn on desktop notifications right after login, if the browser hasn't been asked
 * yet, the person hasn't switched them off and hasn't said "Not now". */
export function shouldOfferDesktopNotifications(enabled: boolean): boolean {
  if (!enabled || desktopPermission() !== 'default') return false
  try {
    return sessionStorage.getItem(JUST_LOGGED_IN) === '1' && localStorage.getItem(PROMPT_DISMISSED) !== '1'
  } catch {
    return false
  }
}

export function dismissDesktopOffer(forGood: boolean) {
  try {
    sessionStorage.removeItem(JUST_LOGGED_IN)
    if (forGood) localStorage.setItem(PROMPT_DISMISSED, '1')
  } catch {
    // Nothing to remember.
  }
}
