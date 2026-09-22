import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { KanbanBoard } from './KanbanBoard'
import type { BoardColumn, IssueListItem } from '@/api/types'

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (s: { user: null }) => unknown) => selector({ user: null }),
}))

vi.mock('@/store/uiStore', () => ({
  useUiStore: (selector: (s: { openIssueModal: () => void }) => unknown) =>
    selector({ openIssueModal: vi.fn() }),
}))

vi.mock('@/api/timesheets', () => ({
  useRunningTimer: () => ({ data: null }),
  useStartTimer: () => ({ mutate: vi.fn() }),
  useStopTimer: () => ({ mutate: vi.fn() }),
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

const columns: BoardColumn[] = [
  { name: 'To Do', status_ids: [1], wip_limit: null },
  { name: 'In Progress', status_ids: [2], wip_limit: 2 },
  { name: 'Done', status_ids: [3], wip_limit: null },
]

describe('KanbanBoard', () => {
  it('shows an empty message when there are no issues', () => {
    render(<KanbanBoard issues={[]} columns={columns} onMoveIssue={vi.fn()} emptyMessage="Nothing here yet." />)
    expect(screen.getByText('Nothing here yet.')).toBeInTheDocument()
  })

  it('renders each column and places cards under their matching status', () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Fix the login flow', status: { id: 1, name: 'To Do', category: 'todo', order: 0 } }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Ship the dashboard', status: { id: 3, name: 'Done', category: 'done', order: 2 } }),
    ]
    render(<KanbanBoard issues={issues} columns={columns} onMoveIssue={vi.fn()} />)

    expect(screen.getByText('To Do')).toBeInTheDocument()
    expect(screen.getByText('In Progress')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('Fix the login flow')).toBeInTheDocument()
    expect(screen.getByText('Ship the dashboard')).toBeInTheDocument()
  })

  it('flags a column as over its WIP limit', () => {
    const issues = [
      makeIssue({ id: 1, status: { id: 2, name: 'In Progress', category: 'in_progress', order: 1 } }),
      makeIssue({ id: 2, status: { id: 2, name: 'In Progress', category: 'in_progress', order: 1 } }),
      makeIssue({ id: 3, status: { id: 2, name: 'In Progress', category: 'in_progress', order: 1 } }),
    ]
    render(<KanbanBoard issues={issues} columns={columns} onMoveIssue={vi.fn()} />)
    expect(screen.getByText('3 / 2')).toBeInTheDocument()
  })

  it('groups cards into swimlanes when a swimlane mode is set', () => {
    const issues = [
      makeIssue({ id: 1, project_key: 'TRK', summary: 'TRK issue' }),
      makeIssue({ id: 2, project_key: 'OPS', summary: 'OPS issue' }),
    ]
    render(
      <KanbanBoard
        issues={issues}
        columns={columns}
        onMoveIssue={vi.fn()}
        defaultSwimlaneMode="project"
        availableSwimlanes={['none', 'project']}
      />,
    )
    expect(screen.getByText(/OPS \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/TRK \(1\)/)).toBeInTheDocument()
  })
})
