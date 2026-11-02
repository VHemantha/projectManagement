import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { IssueTable } from './IssueTable'
import type { IssueListItem } from '@/api/types'

const download = vi.hoisted(() => vi.fn())
vi.mock('@/api/issues', () => ({
  usePatchIssueField: () => ({ mutate: vi.fn() }),
  useBulkArchive: () => ({ mutate: vi.fn(), isPending: false }),
  downloadTasksExcel: download,
}))

// Saved layouts: tests can seed one per table via `savedLayouts`.
const savedLayouts: Record<string, unknown> = {}
vi.mock('@/api/tablePreferences', () => ({
  useTablePreferences: () => ({ data: savedLayouts }),
  useSaveTablePreference: () => vi.fn(),
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

describe('IssueTable', () => {
  it('shows actual vs budgeted time when those columns are turned on', () => {
    savedLayouts['time-test'] = { columnVisibility: { budgeted: true, actual: true, variance: true } }
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Over', budgeted_hours: 4, actual_hours: 5.5 }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Under', budgeted_hours: 8, actual_hours: 2 }),
    ]
    render(<IssueTable tableId="time-test" issues={issues} />)
    expect(screen.getByText('1.5h over')).toBeInTheDocument()
    expect(screen.getByText('6h left')).toBeInTheDocument()
    expect(screen.getByText('5.5h')).toBeInTheDocument()
  })

  it('lists every labelled column in the Columns menu, including field-name columns', async () => {
    render(<IssueTable tableId="menu-test" issues={[makeIssue({ id: 1, key: 'TRK-1', summary: 'x' })]} />)
    await userEvent.click(screen.getByRole('button', { name: /Columns/ }))
    for (const label of ['Key', 'Summary', 'Status', 'Priority', 'Due', 'Actual']) {
      expect(await screen.findByRole('checkbox', { name: label })).toBeInTheDocument()
    }
  })

  it('does not render cells for hidden columns', () => {
    render(<IssueTable tableId="test" issues={[makeIssue({ id: 1, key: 'TRK-1', summary: 'x' })]} />)
    const headerCount = screen.getAllByRole('columnheader').length
    const cellCount = screen.getAllByRole('cell').length
    expect(cellCount).toBe(headerCount)
  })


  it('shows an empty message when there are no issues', () => {
    render(<IssueTable tableId="test" issues={[]} emptyMessage="No issues found." />)
    expect(screen.getByText('No issues found.')).toBeInTheDocument()
  })

  it('renders a row per issue with key and summary', () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', summary: 'Fix the login flow' }),
      makeIssue({ id: 2, key: 'TRK-2', summary: 'Ship the dashboard' }),
    ]
    render(<IssueTable tableId="test" issues={issues} />)
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
    render(<IssueTable tableId="test" issues={issues} />)

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
    render(<IssueTable tableId="test" issues={issues} groupBy="status" />)
    expect(screen.getByText('To Do (2)')).toBeInTheDocument()
    expect(screen.getByText('Done (1)')).toBeInTheDocument()
  })

  it('orders status groups like the board columns, not alphabetically', () => {
    const issues = [
      makeIssue({ id: 1, key: 'TRK-1', status: { id: 6, name: 'Done', category: 'done', order: 5 } }),
      makeIssue({ id: 2, key: 'TRK-2', status: { id: 5, name: 'Blocked', category: 'in_progress', order: 4 } }),
      makeIssue({ id: 3, key: 'TRK-3', status: { id: 1, name: 'Backlog', category: 'todo', order: 0 } }),
      makeIssue({ id: 4, key: 'TRK-4', status: { id: 3, name: 'In progress', category: 'in_progress', order: 2 } }),
    ]
    render(<IssueTable tableId="test" issues={issues} groupBy="status" />)
    const headers = screen.getAllByText(/\(1\)$/).map((el) => el.textContent)
    expect(headers).toEqual(['Backlog (1)', 'In progress (1)', 'Blocked (1)', 'Done (1)'])
  })

  // AFIT, 1 Nov 2026: stage counts and the status filter follow the board's own stage names.
  it('counts each stage by its real name and filters by the stages picked', async () => {
    const stage = (id: number, name: string, order: number, category = 'in_progress') => ({ id, name, category, order }) as IssueListItem['status']
    const issues = [
      makeIssue({ id: 1, key: 'A-1', summary: 'One', status: stage(1, 'To Start', 0, 'todo') }),
      makeIssue({ id: 2, key: 'A-2', summary: 'Two', status: stage(2, 'Sent to Client', 3) }),
      makeIssue({ id: 3, key: 'B-1', summary: 'Three', project_key: 'B', status: stage(9, 'Sent to Client', 3) }),
      makeIssue({ id: 4, key: 'A-3', summary: 'Four', status: stage(4, 'Complete', 6, 'done') }),
    ]
    render(<IssueTable tableId="stages" issues={issues} />)
    const chips = within(screen.getByRole('group', { name: 'Tasks by stage' })).getAllByRole('button')
    expect(chips.map((c) => c.textContent)).toEqual(['To Start 1', 'Sent to Client 2', 'Complete 1'])

    await userEvent.click(chips[1])
    expect(screen.queryByText('One')).not.toBeInTheDocument()
    expect(screen.getByText('Two')).toBeInTheDocument()
    expect(screen.getByText('Three')).toBeInTheDocument()
    await userEvent.click(chips[2])
    expect(screen.getByText('Four')).toBeInTheDocument()
    expect(screen.getByText('3 tasks')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Filter by status'), 'To Start')
    expect(screen.getByText('One')).toBeInTheDocument()
    expect(screen.queryByText('Two')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear status filter' }))
    expect(screen.getByText('4 tasks')).toBeInTheDocument()
  })

  it('downloads every task listed, all pages, as filtered and sorted, to Excel', async () => {
    const issues = Array.from({ length: 55 }, (_, i) =>
      makeIssue({ id: i + 1, key: `P-${i + 1}`, summary: i % 2 ? `Odd ${i + 1}` : `Even ${i + 1}` }),
    )
    render(<IssueTable tableId="excel" issues={issues} />)
    await userEvent.type(screen.getByPlaceholderText('Search by key or summary…'), 'Even')
    await userEvent.click(screen.getByRole('button', { name: /Download Excel/ }))
    const keys = download.mock.calls[0][0] as string[]
    expect(keys).toHaveLength(28)
    expect(keys[0]).toBe('P-1')
    expect(keys).not.toContain('P-2')
  }, 30_000)

  it('shows due dates as DD-MM-YY', () => {
    render(<IssueTable tableId="due" issues={[makeIssue({ id: 1, due_date: '2026-11-02' })]} />)
    expect(screen.getByText('02-11-26')).toBeInTheDocument()
  })

  it('pages through every task, however many', async () => {
    const issues = Array.from({ length: 60 }, (_, i) => makeIssue({ id: i + 1, key: `P-${i + 1}`, summary: `Task ${i + 1}` }))
    render(<IssueTable tableId="pages" issues={issues} />)
    expect(screen.getByText('Task 50')).toBeInTheDocument()
    expect(screen.queryByText('Task 51')).not.toBeInTheDocument()
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(screen.getByText('Task 60')).toBeInTheDocument()
    expect(screen.getByText('51–60 of 60')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    await userEvent.selectOptions(screen.getByDisplayValue('50'), '200')
    expect(screen.getByText('Task 1')).toBeInTheDocument()
    expect(screen.getByText('Task 60')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument()
  }, 30_000)
})
