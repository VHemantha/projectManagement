import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { addDays, format, subDays } from 'date-fns'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { AllIssuesBoardPage } from './AllIssuesBoardPage'
import { TasksSummary } from './TasksSummary'
import type { IssueListItem } from '@/api/types'

const day = (d: Date) => format(d, 'yyyy-MM-dd')
const issue = (over: Partial<IssueListItem>) =>
  ({ id: 1, key: 'RWCA-1', project_key: 'RWCA', summary: 'Job', status: { id: 1, name: 'To do', category: 'todo' }, priority: 'medium',
     assignee: { id: 2, display_name: 'Pat' }, due_date: null, budgeted_hours: null, actual_hours: 0, group: '', ...over }) as unknown as IssueListItem

const mocks = vi.hoisted(() => ({ query: {} as Record<string, unknown>, issues: [] as unknown[] }))

vi.mock('@/api/issues', () => ({
  useIssues: (q: Record<string, unknown>) => {
    mocks.query = q
    return { data: { results: mocks.issues, count: mocks.issues.length }, isLoading: false }
  },
  useMoveIssue: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/api/teams', () => ({ useTeams: () => ({ data: [{ id: 4, name: 'Team 4', parent: null }] }) }))
vi.mock('@/api/clients', () => ({ useClients: () => ({ data: [{ id: 5, name: 'RWCA' }] }) }))
vi.mock('./crossProjectBoard', () => ({ useCrossProjectBoard: () => ({ columns: [], cardConfigByProject: {}, isLoading: false, resolveStatus: () => null }) }))
vi.mock('./KanbanBoard', () => ({ KanbanBoard: () => <div>kanban board</div> }))
vi.mock('@/features/tables/IssueTable', () => ({ IssueTable: ({ issues }: { issues: unknown[] }) => <div>task list of {issues.length}</div> }))
vi.mock('@/features/projects/CreateClientDialog', () => ({ CreateClientDialog: () => null }))

function Where() {
  const { search } = useLocation()
  return <div data-testid="where">{search}</div>
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/projects/all-issues" element={<><AllIssuesBoardPage /><Where /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('The tasks of a workspace / sub-workspace', () => {
  it('is titled by the selection and filtered by workspace and sub-workspace', () => {
    mocks.issues = [issue({})]
    renderAt('/projects/all-issues?team=4&client=5')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Team 4 › RWCA')
    expect(mocks.query).toMatchObject({ team: 4, client: 5 })
    expect(screen.getByText('kanban board')).toBeVisible()
  })

  it('shows the same tasks as a list and as a summary, and keeps the view in the address', async () => {
    mocks.issues = [issue({}), issue({ id: 2, key: 'RWCA-2' })]
    renderAt('/projects/all-issues?team=4')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Team 4')
    await userEvent.click(screen.getByRole('tab', { name: 'Tasks' }))
    expect(screen.getByText('task list of 2')).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('team=4&view=tasks')
    await userEvent.click(screen.getByRole('tab', { name: 'Summary' }))
    expect(screen.getByRole('list', { name: 'Totals' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Kanban' }))
    expect(screen.getByTestId('where')).toHaveTextContent('?team=4')
    expect(screen.getByTestId('where')).not.toHaveTextContent('view')
  })
})

describe('TasksSummary', () => {
  it('counts open, done, overdue, due soon and hours, and breaks them down', () => {
    const today = new Date()
    render(
      <TasksSummary
        issues={[
          issue({ key: 'A', due_date: day(subDays(today, 2)), budgeted_hours: 10, actual_hours: 12, group: 'Rentals' }),
          issue({ key: 'B', due_date: day(addDays(today, 3)), budgeted_hours: 10, actual_hours: 4, assignee: null }),
          issue({ key: 'C', status: { id: 3, name: 'Done', category: 'done' } as IssueListItem['status'], due_date: day(subDays(today, 5)), actual_hours: 2 }),
        ]}
      />,
    )
    const totals = within(screen.getByRole('list', { name: 'Totals' })).getAllByRole('listitem').map((li) => li.textContent)
    expect(totals).toEqual(['2Open', '1Done', '1Overdue', '1Due in the next 7 days', '18.0h / 20.0hLogged / budgeted (90%)', '1Over budget',
      '1Open with nobody assigned'])
    const byPerson = screen.getByRole('region', { name: 'By person' })
    expect(within(byPerson).getByRole('row', { name: /Pat/ })).toHaveTextContent('Pat11114.0h10.0h')
    expect(within(byPerson).getByRole('row', { name: /Unassigned/ })).toHaveTextContent('Unassigned1004.0h10.0h')
    expect(screen.getByRole('region', { name: 'By group' })).toHaveTextContent('Rentals')
  })
})
