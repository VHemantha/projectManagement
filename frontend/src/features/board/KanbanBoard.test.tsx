import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    project_name: 'TrackFlow Web App',
    budgeted_hours: null,
    actual_hours: 0,
    allocated_value: null,
    value_currency: 'USD',
    is_archived: false,
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

    // Column titles, and each card's stage (AFIT, 28 Oct 2026: every card shows its stage).
    expect(screen.getAllByText('To Do')).toHaveLength(2)
    expect(screen.getByText('In Progress')).toBeInTheDocument()
    expect(screen.getAllByText('Done')).toHaveLength(2)
    expect(screen.getByText('Fix the login flow')).toBeInTheDocument()
    expect(screen.getByText('Ship the dashboard')).toBeInTheDocument()
  })

  it('shows each card as "Summary - Project Name"', () => {
    const issues = [makeIssue({ id: 1, summary: 'Bank reconciliation', project_name: 'Pochin Group' })]
    render(<KanbanBoard issues={issues} columns={columns} onMoveIssue={vi.fn()} />)
    expect(screen.getByText('Bank reconciliation')).toHaveTextContent('Bank reconciliation - Pochin Group')
  })

  it("draws each card with its own project's colour coding on a mixed-project board", () => {
    const issues = [
      makeIssue({ id: 1, project_key: 'TRK', summary: 'TRK card', priority: 'high' }),
      makeIssue({ id: 2, project_key: 'OPS', summary: 'OPS card', priority: 'high' }),
    ]
    render(
      <KanbanBoard
        issues={issues}
        columns={columns}
        onMoveIssue={vi.fn()}
        cardConfigByProject={{
          TRK: { cardColorRule: 'priority', cardColors: { priority: { high: '#123456' } } },
          OPS: { cardColorRule: 'none' },
        }}
      />,
    )
    // The summary's parent is the card element that carries the colour.
    const cardOf = (text: string) => screen.getByText(text).parentElement as HTMLElement
    expect(cardOf('TRK card').style.borderLeft).toContain('rgb(18, 52, 86)')
    expect(cardOf('OPS card').style.borderLeft).toBe('')
  })

  it('does not show the task value on cards (AFIT, 28 Oct 2026)', () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Valued', allocated_value: '1200.00', value_currency: 'GBP' }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Unvalued' }),
    ]
    render(<KanbanBoard issues={issues} columns={columns} onMoveIssue={vi.fn()} />)
    expect(screen.queryByText(/1,200/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /task value/i })).not.toBeInTheDocument()
  })

  it('filters cards by priority and label from the toolbar, keeping the columns', async () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Urgent VAT', priority: 'high', labels: [{ id: 1, name: 'VAT', color: '#ccc' }] }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Routine', priority: 'low', status: { id: 3, name: 'Done', category: 'done', order: 2 } }),
    ]
    render(<KanbanBoard issues={issues} columns={columns} onMoveIssue={vi.fn()} />)
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filter by priority' }), 'high')
    expect(screen.getByText('Urgent VAT')).toBeInTheDocument()
    expect(screen.queryByText('Routine')).not.toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByText('Routine')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filter by label' }), 'VAT')
    expect(screen.queryByText('Routine')).not.toBeInTheDocument()
  })

  it('renames a column in place when renaming is allowed', async () => {
    const onRenameColumn = vi.fn(() => Promise.resolve())
    render(
      <KanbanBoard issues={[makeIssue({ id: 1 })]} columns={columns} onMoveIssue={vi.fn()} onRenameColumn={onRenameColumn} />,
    )
    await userEvent.dblClick(screen.getByText('In Progress'))
    const input = screen.getByRole('textbox', { name: 'Column name' })
    await userEvent.clear(input)
    await userEvent.type(input, 'Doing{Enter}')
    expect(onRenameColumn).toHaveBeenCalledWith(1, 'Doing')
    expect(screen.getByText('Doing')).toBeInTheDocument()
  })

  it('shows plain column names when renaming is not allowed', () => {
    render(<KanbanBoard issues={[makeIssue({ id: 1 })]} columns={columns} onMoveIssue={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Rename column name' })).not.toBeInTheDocument()
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

  it('creates a task from a column: the page is told which column and swimlane', async () => {
    const onCreateIssue = vi.fn()
    render(<KanbanBoard issues={[makeIssue({})]} columns={columns} onMoveIssue={vi.fn()} onCreateIssue={onCreateIssue} />)
    await userEvent.click(screen.getByRole('button', { name: 'Create task in In Progress' }))
    expect(onCreateIssue).toHaveBeenCalledWith({ column: columns[1], lane: expect.objectContaining({ id: 'all' }), swimlaneMode: 'none' })
    // Pressing + did not collapse the column (a collapsed column hides its button).
    expect(screen.getByRole('button', { name: 'Create task in In Progress' })).toBeInTheDocument()
  })

  it('has no create button where the page does not allow it', () => {
    render(<KanbanBoard issues={[]} columns={columns} onMoveIssue={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Create task in/ })).not.toBeInTheDocument()
  })
})


describe('Card face (AFIT, 28 Oct 2026)', () => {
  it('shows the stage, priority and deadline, and no task code, time or story points', () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Smith FY26', priority: 'high', due_date: '2020-01-31', actual_hours: 3, budgeted_hours: 8,
        status: { id: 1, name: 'To Do', category: 'todo', order: 0 } }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Jones FY26', status: { id: 3, name: 'Done', category: 'done', order: 2 } }),
    ]
    render(<KanbanBoard issues={issues} columns={columns} onMoveIssue={vi.fn()} />)
    const card = screen.getByText('Smith FY26').closest('[role="button"]') as HTMLElement
    expect(card).toHaveTextContent('To Do')
    expect(card).toHaveTextContent('High')
    expect(card).toHaveTextContent('31 Jan')
    expect(screen.getByTitle('Deadline Fri 31 Jan 2020 (overdue)')).toBeInTheDocument()
    expect(card).not.toHaveTextContent('TRK-1')
    expect(card).not.toHaveTextContent('3h')
    expect(screen.getByText('Jones FY26').closest('[role="button"]')).toHaveTextContent('No deadline')
  })
})
