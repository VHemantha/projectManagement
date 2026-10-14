import { describe, expect, it } from 'vitest'

import { defaultsFromColumn } from './createFromBoard'
import type { Lane } from './laneUtils'

const lane = (id: string): Lane => ({ id, label: id, issues: [] })

describe('defaultsFromColumn', () => {
  it("takes the column's first status, or its category on a board across projects", () => {
    expect(defaultsFromColumn({ column: { name: 'Review', status_ids: [7, 8], wip_limit: null }, lane: lane('all'), swimlaneMode: 'none' }))
      .toEqual({ columnName: 'Review', statusId: 7 })
    expect(defaultsFromColumn({ column: { name: 'In progress', status_ids: [], wip_limit: null, category: 'in_progress' }, lane: lane('all'), swimlaneMode: 'none' }))
      .toEqual({ columnName: 'In progress', statusCategory: 'in_progress' })
  })

  it("takes the swimlane's epic, assignee or project, but not its 'none' lanes", () => {
    const column = { name: 'To do', status_ids: [1], wip_limit: null }
    expect(defaultsFromColumn({ column, lane: lane('42'), swimlaneMode: 'epic' }).epicId).toBe(42)
    expect(defaultsFromColumn({ column, lane: lane('no-epic'), swimlaneMode: 'epic' }).epicId).toBeUndefined()
    expect(defaultsFromColumn({ column, lane: lane('5'), swimlaneMode: 'assignee' }).assigneeId).toBe(5)
    expect(defaultsFromColumn({ column, lane: lane('unassigned'), swimlaneMode: 'assignee' }).assigneeId).toBeUndefined()
    expect(defaultsFromColumn({ column, lane: lane('SMITH'), swimlaneMode: 'project' }).projectKey).toBe('SMITH')
  })
})
