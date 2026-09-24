import { describe, expect, it } from 'vitest'

import { keysToInvalidate } from './useLiveUpdates'

const ev = (kind: string, project: string | null = null, key: string | null = null) =>
  ({ type: 'live.change', kind, project, key }) as Parameters<typeof keysToInvalidate>[0][number]

describe('keysToInvalidate', () => {
  it('an issue change refreshes every issue list/board and that issue', () => {
    const keys = keysToInvalidate([ev('issues', 'TRK', 'TRK-1')]).map((k) => k.queryKey)
    expect(keys).toContainEqual(['issues'])
    expect(keys).toContainEqual(['issue', 'TRK-1'])
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
