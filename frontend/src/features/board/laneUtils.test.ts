import { describe, expect, it } from 'vitest'

import { computeLanes } from './laneUtils'
import type { IssueListItem } from '@/api/types'

function makeIssue(overrides: Partial<IssueListItem>): IssueListItem {
  return {
    id: 1,
    key: 'TRK-1',
    project_key: 'TRK',
    summary: 'Test issue',
    issue_type: { id: 1, name: 'Task', icon: 'check-square', color: '#0C66E4', is_subtask: false, order: 0 },
    status: { id: 1, name: 'To Do', category: 'todo', order: 0 },
    priority: 'medium',
    assignee: null,
    reporter: {
      id: 1,
      email: 'a@example.com',
      username: 'a',
      display_name: 'A User',
      job_title: '',
      avatar: null,
      is_staff: false,
    },
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
    rank: '0',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    resolved_at: null,
    ...overrides,
  }
}

describe('computeLanes', () => {
  it('returns a single unlabeled lane for mode "none"', () => {
    const issues = [makeIssue({ id: 1 }), makeIssue({ id: 2 })]
    const lanes = computeLanes(issues, 'none')
    expect(lanes).toHaveLength(1)
    expect(lanes[0].label).toBeNull()
    expect(lanes[0].issues).toHaveLength(2)
  })

  it('groups by assignee and puts Unassigned last', () => {
    const alice = {
      id: 10,
      email: 'alice@example.com',
      username: 'alice',
      display_name: 'Alice',
      job_title: '',
      avatar: null,
      is_staff: false,
    }
    const issues = [
      makeIssue({ id: 1, assignee: null }),
      makeIssue({ id: 2, assignee: alice }),
      makeIssue({ id: 3, assignee: alice }),
    ]
    const lanes = computeLanes(issues, 'assignee')
    expect(lanes.map((l) => l.label)).toEqual(['Alice', 'Unassigned'])
    expect(lanes[0].issues).toHaveLength(2)
    expect(lanes[1].issues).toHaveLength(1)
  })

  it('groups by epic and puts "No epic" last', () => {
    const epic = { id: 5, key: 'TRK-5', epic_name: 'Big Epic', epic_color: '#8777D9' }
    const issues = [
      makeIssue({ id: 1, epic: null }),
      makeIssue({ id: 2, epic }),
    ]
    const lanes = computeLanes(issues, 'epic')
    expect(lanes.map((l) => l.label)).toEqual(['Big Epic', 'No epic'])
  })

  it('groups by project key', () => {
    const issues = [
      makeIssue({ id: 1, project_key: 'OPS' }),
      makeIssue({ id: 2, project_key: 'TRK' }),
      makeIssue({ id: 3, project_key: 'TRK' }),
    ]
    const lanes = computeLanes(issues, 'project')
    expect(lanes.map((l) => l.label)).toEqual(['OPS', 'TRK'])
    expect(lanes[1].issues).toHaveLength(2)
  })

  it('falls back to a single lane for "parent" mode', () => {
    const issues = [makeIssue({ id: 1 })]
    const lanes = computeLanes(issues, 'parent')
    expect(lanes).toHaveLength(1)
    expect(lanes[0].label).toBeNull()
  })
})
