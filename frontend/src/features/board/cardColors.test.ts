import { describe, expect, it } from 'vitest'

import { DEFAULT_DUE_DATE_COLORS, DEFAULT_PRIORITY_COLORS, cardAccentColor, dueDateBucket, withAlpha } from './cardColors'
import type { IssueListItem } from '@/api/types'

function makeIssue(overrides: Partial<IssueListItem>): IssueListItem {
  return {
    id: 1,
    key: 'TRK-1',
    project_key: 'TRK',
    project_name: 'TrackFlow Web App',
    summary: 'Card',
    issue_type: { id: 3, name: 'Task', icon: 'check-square', color: '#0c66e4', is_subtask: false, order: 0 },
    status: { id: 1, name: 'To Do', category: 'todo', order: 0 },
    priority: 'high',
    assignee: null,
    reporter: null,
    preparer: null,
    reviewer: null,
    current_responsible: null,
    epic: null,
    parent_id: null,
    sprint: null,
    story_points: null,
    start_date: null,
    due_date: null,
    labels: [],
    rank: '000001',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    resolved_at: null,
    ...overrides,
  } as IssueListItem
}

const TODAY = new Date(2026, 8, 24) // 24 Sep 2026, local time

describe('dueDateBucket', () => {
  it('buckets open issues by how soon they are due', () => {
    expect(dueDateBucket(makeIssue({ due_date: '2026-09-23' }), TODAY)).toBe('overdue')
    expect(dueDateBucket(makeIssue({ due_date: '2026-09-24' }), TODAY)).toBe('due_soon')
    expect(dueDateBucket(makeIssue({ due_date: '2026-09-27' }), TODAY)).toBe('due_soon')
    expect(dueDateBucket(makeIssue({ due_date: '2026-09-28' }), TODAY)).toBe('on_track')
  })

  it('never colours done issues or issues without a due date', () => {
    expect(dueDateBucket(makeIssue({ due_date: null }), TODAY)).toBeNull()
    const done = { id: 9, name: 'Done', category: 'done' as const, order: 3 }
    expect(dueDateBucket(makeIssue({ due_date: '2020-01-01', status: done }), TODAY)).toBeNull()
  })
})

describe('cardAccentColor', () => {
  it('uses built-in colours unless the board overrides them', () => {
    const issue = makeIssue({ priority: 'high' })
    expect(cardAccentColor(issue, 'priority', {})).toBe(DEFAULT_PRIORITY_COLORS.high)
    expect(cardAccentColor(issue, 'priority', { priority: { high: '#123456' } })).toBe('#123456')
    expect(cardAccentColor(issue, 'issue_type', {})).toBe('#0c66e4')
    expect(cardAccentColor(issue, 'issue_type', { issue_type: { '3': '#00ff00' } })).toBe('#00ff00')
  })

  it('colours overdue cards by the due-date rule', () => {
    const overdue = makeIssue({ due_date: '2000-01-01' })
    expect(cardAccentColor(overdue, 'due_date', {})).toBe(DEFAULT_DUE_DATE_COLORS.overdue)
    expect(cardAccentColor(overdue, 'due_date', { due_date: { overdue: '#aa0000' } })).toBe('#aa0000')
  })

  it('returns nothing when there is no rule', () => {
    expect(cardAccentColor(makeIssue({}), 'none', {})).toBeUndefined()
  })
})

describe('withAlpha', () => {
  it('turns hex into translucent rgba and leaves non-hex alone', () => {
    expect(withAlpha('#ff0000', 0.5)).toBe('rgba(255, 0, 0, 0.5)')
    expect(withAlpha('var(--x)', 0.5)).toBe('var(--x)')
  })
})
