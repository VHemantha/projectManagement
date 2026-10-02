import { afterEach, describe, expect, it } from 'vitest'

import { resolveTab, tabForLegacySection, workspaceTabs } from './workspaceTabs'
import { FEATURES } from '@/lib/features'

const kanban = { project_type: 'kanban' as const }
const scrum = { project_type: 'scrum' as const }
const ids = (p: typeof kanban | typeof scrum) => workspaceTabs(p).map((t) => t.id)

afterEach(() => {
  FEATURES.scrum = false
  FEATURES.summary = false
})

describe('workspace tabs', () => {
  it('puts Kanban first and hides Scrum views and Summary by default', () => {
    expect(ids(kanban)).toEqual(['kanban', 'jobs', 'timeline', 'settings'])
    // A Scrum workspace looks like a Kanban one while the Scrum feature is off.
    expect(ids(scrum)).toEqual(['kanban', 'jobs', 'timeline', 'settings'])
    expect(workspaceTabs(scrum)[0].label).toBe('Kanban')
  })

  it('restores the Scrum views and Summary when their flags are on', () => {
    FEATURES.scrum = true
    FEATURES.summary = true
    expect(ids(scrum)).toEqual(['kanban', 'summary', 'backlog', 'jobs', 'timeline', 'reports', 'settings'])
    expect(workspaceTabs(scrum)[0].label).toBe('Sprint board')
    // Kanban workspaces never get the sprint-only tabs.
    expect(ids(kanban)).toEqual(['kanban', 'summary', 'jobs', 'timeline', 'settings'])
  })

  it('falls back to Kanban for missing, unknown or hidden tabs', () => {
    expect(resolveTab(null, kanban)).toBe('kanban')
    expect(resolveTab('nope', kanban)).toBe('kanban')
    expect(resolveTab('summary', kanban)).toBe('kanban')
    expect(resolveTab('backlog', scrum)).toBe('kanban')
    expect(resolveTab('jobs', kanban)).toBe('jobs')
  })

  it('maps old sub-page URLs to tabs', () => {
    expect(tabForLegacySection('board')).toBe('kanban')
    expect(tabForLegacySection('issues')).toBe('jobs')
    expect(tabForLegacySection('settings')).toBe('settings')
    expect(tabForLegacySection('whatever')).toBe('kanban')
  })
})
