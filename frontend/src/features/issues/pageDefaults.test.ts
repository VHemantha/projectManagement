import { describe, expect, it } from 'vitest'

import { pageDefaults } from './pageDefaults'

describe('pageDefaults', () => {
  it('reads what the page is about from its address', () => {
    expect(pageDefaults('/projects/SMITH', '?tab=board')).toEqual({ projectKey: 'SMITH' })
    expect(pageDefaults('/projects/SMITH/epics/SMITH-4/board', '')).toEqual({ projectKey: 'SMITH' })
    expect(pageDefaults('/projects/all-issues', '?team=3&client=12')).toEqual({ teamId: 3, clientId: 12 })
    expect(pageDefaults('/projects/all-issues', '?no_team=true')).toEqual({})
    expect(pageDefaults('/workspaces/7', '')).toEqual({ teamId: 7 })
    expect(pageDefaults('/chat', '')).toEqual({})
  })
})
