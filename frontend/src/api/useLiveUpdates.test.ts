import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CATCH_UP_MIN_INTERVAL_MS, keysToInvalidate, useLiveUpdates } from './useLiveUpdates'
import { useAuthStore } from '@/store/authStore'

class FakeSocket {
  static all: FakeSocket[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((m: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  constructor() {
    FakeSocket.all.push(this)
  }
  close() {
    this.onclose?.()
  }
}

describe('useLiveUpdates', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    FakeSocket.all = []
  })

  it('after a dropped connection it reloads what is on screen, but not on every reconnect', () => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', FakeSocket)
    useAuthStore.setState({ accessToken: 'token' })
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
    renderHook(() => useLiveUpdates(), { wrapper })

    const reconnect = () => {
      act(() => FakeSocket.all.at(-1)!.close())
      act(() => vi.advanceTimersByTime(10_000))
      act(() => FakeSocket.all.at(-1)!.onopen?.())
    }
    act(() => FakeSocket.all[0].onopen?.())
    expect(invalidate).not.toHaveBeenCalled() // the first connection has nothing to catch up on
    reconnect()
    const afterFirst = invalidate.mock.calls.length
    expect(afterFirst).toBeGreaterThan(0)
    reconnect()
    reconnect()
    expect(invalidate.mock.calls.length).toBe(afterFirst) // a flapping connection does not reload again and again
    act(() => vi.advanceTimersByTime(CATCH_UP_MIN_INTERVAL_MS))
    reconnect()
    expect(invalidate.mock.calls.length).toBeGreaterThan(afterFirst)
  })
})

const ev = (kind: string, project: string | null = null, key: string | null = null) =>
  ({ type: 'live.change', kind, project, key }) as Parameters<typeof keysToInvalidate>[0][number]

describe('keysToInvalidate', () => {
  it('an issue change refreshes every issue list/board and that issue', () => {
    const keys = keysToInvalidate([ev('issues', 'TRK', 'TRK-1')]).map((k) => k.queryKey)
    expect(keys).toContainEqual(['issues'])
    expect(keys).toContainEqual(['issue', 'TRK-1'])
  })

  it("logged time refreshes the open workspace's details (its actual hours)", () => {
    const keys = keysToInvalidate([ev('issues', 'TRK', 'TRK-1')])
    expect(keys).toContainEqual({ queryKey: ['projects', 'TRK'], exact: true })
  })

  it("a board change refreshes that project's board settings (used by every board showing it)", () => {
    const keys = keysToInvalidate([ev('board', 'TRK')]).map((k) => k.queryKey)
    expect(keys).toContainEqual(['projects', 'TRK', 'board'])
    expect(keys).toContainEqual(['projects', 'TRK', 'workflow-transitions'])
  })

  it('a burst of notices collapses to one refetch per query key', () => {
    const keys = keysToInvalidate([ev('issues', 'TRK', 'TRK-1'), ev('issues', 'TRK', 'TRK-1'), ev('issues', 'OPS', 'OPS-2')])
    const serialized = keys.map((k) => JSON.stringify(k))
    expect(new Set(serialized).size).toBe(serialized.length)
    expect(keys.filter((k) => JSON.stringify(k.queryKey) === '["issues"]')).toHaveLength(1)
  })

  it('sprint changes also refresh issue lists (bulk moves skip per-issue notices)', () => {
    const keys = keysToInvalidate([ev('sprints', 'TRK')]).map((k) => k.queryKey)
    expect(keys).toContainEqual(['sprints', 'TRK'])
    expect(keys).toContainEqual(['issues'])
  })
})
