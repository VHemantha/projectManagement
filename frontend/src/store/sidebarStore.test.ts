import { describe, expect, it } from 'vitest'

import { useSidebarStore } from './sidebarStore'

describe('Sidebars (AFIT, 1 Nov 2026)', () => {
  it("opening the Kanban board's panel collapses the main sidebar", () => {
    const s = useSidebarStore.getState()
    s.setOpen('projectsTree', false)
    s.setMainExpanded(true)
    useSidebarStore.getState().toggle('projectsTree')
    expect(useSidebarStore.getState().mainExpanded).toBe(false)
    useSidebarStore.getState().setMainExpanded(true)
    useSidebarStore.getState().setOpen('jobFilters', true)
    expect(useSidebarStore.getState().mainExpanded).toBe(true)
    useSidebarStore.getState().setOpen('projectsTree', true)
    expect(useSidebarStore.getState().mainExpanded).toBe(false)
  })
})
