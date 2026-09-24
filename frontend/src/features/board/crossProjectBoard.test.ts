import { describe, expect, it } from 'vitest'

import { statusForCategory } from './crossProjectBoard'
import type { Board, IssueListItem } from '@/api/types'

const board = {
  id: 1,
  name: 'B',
  board_type: 'kanban',
  swimlane_mode: 'none',
  card_fields: [],
  card_color_rule: 'none',
  card_colors: {},
  card_color_style: 'stripe',
  filters: null,
  statuses: [
    { id: 1, name: 'To Do', category: 'todo', order: 0, issue_count: 0 },
    { id: 2, name: 'In Progress', category: 'in_progress', order: 1, issue_count: 0 },
    { id: 3, name: 'Done', category: 'done', order: 2, issue_count: 0 },
    { id: 9, name: 'QA', category: 'in_progress', order: 5, issue_count: 0 },
  ],
  // QA was dragged ahead of In Progress on this project's board.
  column_config: [
    { name: 'To Do', status_ids: [1], wip_limit: null },
    { name: 'QA', status_ids: [9], wip_limit: null },
    { name: 'In Progress', status_ids: [2], wip_limit: null },
    { name: 'Done', status_ids: [3], wip_limit: null },
  ],
} as unknown as Board

const issueIn = (id: number, category: 'todo' | 'in_progress' | 'done') =>
  ({ status: { id, name: '', category, order: 0 } }) as IssueListItem

describe('statusForCategory', () => {
  it("uses the first status of that category in the project's column order", () => {
    expect(statusForCategory(issueIn(1, 'todo'), 'in_progress', board)).toBe(9)
    expect(statusForCategory(issueIn(1, 'todo'), 'done', board)).toBe(3)
  })

  it('keeps the current status when a card is reordered within its category', () => {
    // Previously a QA card reordered in "In Progress" was silently moved to the In Progress status.
    expect(statusForCategory(issueIn(9, 'in_progress'), 'in_progress', board)).toBe(9)
  })

  it('returns null when the project board is unknown', () => {
    expect(statusForCategory(issueIn(1, 'todo'), 'done', undefined)).toBeNull()
  })
})
