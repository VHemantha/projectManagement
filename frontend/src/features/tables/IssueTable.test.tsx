import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { IssueTable } from './IssueTable'
import type { IssueListItem } from '@/api/types'

vi.mock('@/api/issues', () => ({
  usePatchIssueField: () => ({ mutate: vi.fn() }),
}))

vi.mock('@/api/users', () => ({
  useUsers: () => ({ data: [] }),
}))

vi.mock('@/api/timesheets', () => ({
  useRunningTimer: () => ({ data: null }),
  useStartTimer: () => ({ mutate: vi.fn() }),
  useStopTimer: () => ({ mutate: vi.fn() }),
}))

vi.mock('@/store/uiStore', () => ({
  useUiStore: Object.assign(
    (selector: (s: { openIssueModal: () => void }) => unknown) => selector({ openIssueModal: vi.fn() }),
    { getState: () => ({ openIssueModal: vi.fn() }) },
  ),
}))

function makeIssue(overrides: Partial<IssueListItem>): IssueListItem {
  return {
    id: 1,
    key: 'TRK-1',
    project_key: 'TRK',
    summary: 'Fix the login flow',
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

describe('IssueTable', () => {
  it('shows an empty message when there are no issues', () => {
    render(<IssueTable issues={[]} emptyMessage="No issues found." />)
    expect(screen.getByText('No issues found.')).toBeInTheDocument()
  })

  it('renders a row per issue with key and summary', () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Fix the login flow' }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Ship the dashboard' }),
    ]
    render(<IssueTable issues={issues} />)
    expect(screen.getByText('TRK-1')).toBeInTheDocument()
    expect(screen.getByText('Fix the login flow')).toBeInTheDocument()
    expect(screen.getByText('TRK-2')).toBeInTheDocument()
    expect(screen.getByText('Ship the dashboard')).toBeInTheDocument()
  })

  it('filters rows by the search box', async () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Fix the login flow' }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Ship the dashboard' }),
    ]
    render(<IssueTable issues={issues} />)

    const user = userEvent.setup()
    await user.type(screen.getByPlaceholderText('Search by key or summary…'), 'dashboard')

    expect(screen.queryByText('Fix the login flow')).not.toBeInTheDocument()
    expect(screen.getByText('Ship the dashboard')).toBeInTheDocument()
  })

  it('renders a group header row with a count when grouped by status', () => {
    const issues = [
      makeIssue({ id: 1, status: { id: 1, name: 'To Do', category: 'todo', order: 0 } }),
      makeIssue({ id: 2, status: { id: 1, name: 'To Do', category: 'todo', order: 0 } }),
      makeIssue({ id: 3, status: { id: 2, name: 'Done', category: 'done', order: 1 } }),
    ]
    render(<IssueTable issues={issues} groupBy="status" />)
    expect(screen.getByText('To Do (2)')).toBeInTheDocument()
    expect(screen.getByText('Done (1)')).toBeInTheDocument()
  })
})
