import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  dismissDesktopOffer,
  markJustLoggedIn,
  shouldNotify,
  shouldOfferDesktopNotifications,
  showDesktopNotification,
} from './desktopNotifications'
import { useDesktopNotifications } from './useDesktopNotifications'
import { emitInboxEvent, type InboxEvent } from '@/api/inboxEvents'
import { useAuthStore } from '@/store/authStore'

const dm: InboxEvent = {
  id: 'message-7',
  kind: 'message',
  tag: 'message-7',
  title: 'Ann',
  body: 'Lunch?',
  url: '/chat?channel=3',
  channel_id: 3,
  created_at: '2026-10-01T10:00:00Z',
}
const assigned: InboxEvent = { ...dm, id: 'notification-9', kind: 'notification', tag: 'notification-9', channel_id: null, url: '/workspaces/TRK/issues/TRK-1' }

// A stand-in for the browser's Notification API.
const shown: { title: string; options: NotificationOptions; instance: FakeNotification }[] = []
class FakeNotification {
  static permission: NotificationPermission = 'granted'
  static requestPermission = vi.fn(async () => FakeNotification.permission)
  onclick: (() => void) | null = null
  close = vi.fn()
  constructor(title: string, options: NotificationOptions) {
    shown.push({ title, options, instance: this })
  }
}

beforeEach(() => {
  shown.length = 0
  FakeNotification.permission = 'granted'
  vi.stubGlobal('Notification', FakeNotification)
  sessionStorage.clear()
  localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

describe('shouldNotify', () => {
  const ctx = { enabled: true, permission: 'granted' as const, focused: false, pathname: '/' }

  it('shows anything when the app is in the background', () => {
    expect(shouldNotify(dm, ctx)).toBe(true)
    expect(shouldNotify(assigned, ctx)).toBe(true)
  })

  it('respects the setting and the browser permission', () => {
    expect(shouldNotify(dm, { ...ctx, enabled: false })).toBe(false)
    expect(shouldNotify(dm, { ...ctx, permission: 'default' })).toBe(false)
    expect(shouldNotify(dm, { ...ctx, permission: 'denied' })).toBe(false)
  })

  it('stays quiet when the inbox is open and focused', () => {
    expect(shouldNotify(dm, { ...ctx, focused: true, pathname: '/chat' })).toBe(false)
    // Focused elsewhere in the app: a new DM still pops up; bell items stay in the bell.
    expect(shouldNotify(dm, { ...ctx, focused: true, pathname: '/workspaces/TRK' })).toBe(true)
    expect(shouldNotify(assigned, { ...ctx, focused: true, pathname: '/workspaces/TRK' })).toBe(false)
  })
})

it('clicking a notification focuses the app and opens the message', () => {
  const open = vi.fn()
  const focus = vi.spyOn(window, 'focus').mockImplementation(() => {})
  showDesktopNotification(dm, open)
  expect(shown[0].title).toBe('Ann')
  expect(shown[0].options).toMatchObject({ body: 'Lunch?', tag: 'message-7' })
  shown[0].instance.onclick?.()
  expect(focus).toHaveBeenCalled()
  expect(open).toHaveBeenCalledWith('/chat?channel=3')
  expect(shown[0].instance.close).toHaveBeenCalled()
})

describe('permission offer', () => {
  it('is only made right after login, while the browser has not been asked', () => {
    FakeNotification.permission = 'default'
    expect(shouldOfferDesktopNotifications(true)).toBe(false) // plain page load
    markJustLoggedIn()
    expect(shouldOfferDesktopNotifications(true)).toBe(true)
    expect(shouldOfferDesktopNotifications(false)).toBe(false) // switched off
    FakeNotification.permission = 'granted'
    expect(shouldOfferDesktopNotifications(true)).toBe(false)
  })

  it('"Not now" is remembered', () => {
    FakeNotification.permission = 'default'
    markJustLoggedIn()
    dismissDesktopOffer(true)
    markJustLoggedIn()
    expect(shouldOfferDesktopNotifications(true)).toBe(false)
  })
})

describe('useDesktopNotifications', () => {
  const wrapper = (path: string) =>
    function Wrapper({ children }: { children: ReactNode }) {
      return <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
    }

  beforeEach(() => {
    useAuthStore.setState({ accessToken: 'token', user: { desktop_notifications: true } as never })
  })

  it('turns live inbox events into desktop notifications (once each)', () => {
    vi.spyOn(document, 'hasFocus').mockReturnValue(false)
    const { unmount } = renderHook(() => useDesktopNotifications(), { wrapper: wrapper('/workspaces/TRK') })
    emitInboxEvent(dm)
    emitInboxEvent(dm)
    expect(shown.map((s) => s.title)).toEqual(['Ann'])
    unmount()
    emitInboxEvent({ ...dm, id: 'message-8' })
    expect(shown).toHaveLength(1)
  })

  it('does nothing when switched off', () => {
    vi.spyOn(document, 'hasFocus').mockReturnValue(false)
    useAuthStore.setState({ user: { desktop_notifications: false } as never })
    renderHook(() => useDesktopNotifications(), { wrapper: wrapper('/') })
    emitInboxEvent(dm)
    expect(shown).toHaveLength(0)
  })

  it('does nothing while the inbox is open and focused', () => {
    vi.spyOn(document, 'hasFocus').mockReturnValue(true)
    window.history.pushState({}, '', '/chat?channel=3')
    renderHook(() => useDesktopNotifications(), { wrapper: wrapper('/chat') })
    emitInboxEvent(dm)
    expect(shown).toHaveLength(0)
    window.history.pushState({}, '', '/')
  })
})
