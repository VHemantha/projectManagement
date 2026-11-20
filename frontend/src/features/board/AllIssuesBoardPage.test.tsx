import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { addDays, format, subDays } from 'date-fns'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { AllIssuesBoardPage } from './AllIssuesBoardPage'
import { TasksSummary } from './TasksSummary'
import type { IssueListItem } from '@/api/types'
import { useUiStore } from '@/store/uiStore'

const day = (d: Date) => format(d, 'yyyy-MM-dd')
const issue = (over: Partial<IssueListItem>) =>
  ({ id: 1, key: 'RWCA-1', project_key: 'RWCA', summary: 'Job', status: { id: 1, name: 'To do', category: 'todo' }, priority: 'medium',
     assignee: { id: 2, display_name: 'Pat' }, due_date: null, budgeted_hours: null, actual_hours: 0, group: '', ...over }) as unknown as IssueListItem

const mocks = vi.hoisted(() => ({ query: {} as Record<string, unknown>, issues: [] as unknown[], settingsOpen: false,
  boards: {} as Record<string, { can_configure?: boolean }>, columnsOpen: false }))

vi.mock('@/api/issues', () => ({
  useAllIssues: (q: Record<string, unknown>) => {
    mocks.query = q
    return { data: { results: mocks.issues, count: mocks.issues.length }, isLoading: false }
  },
  useMoveIssue: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/api/teams', () => ({
  useTeams: () => ({ data: [{ id: 4, name: 'Team 4', parent: null }] }),
  useTeam: (id?: string) => ({ data: id ? { id: Number(id), name: 'Team 4' } : undefined }),
}))
vi.mock('@/features/teams/TeamSubWorkspacesTab', () => ({ TeamSubWorkspacesTab: ({ team }: { team: { name: string } }) => <div>sub-workspaces of {team.name}</div> }))
vi.mock('@/features/teams/TeamGoalsTab', () => ({ TeamGoalsTab: () => <div>goals tab</div> }))
vi.mock('@/features/teams/TeamMembersTab', () => ({ TeamMembersTab: () => <div>members tab</div> }))
vi.mock('./BoardColumnsDialog', () => ({
  BoardColumnsDialog: ({ open }: { open: boolean }) => {
    mocks.columnsOpen = open
    return open ? <div>columns window</div> : null
  },
}))
vi.mock('@/api/clients', () => ({ useClients: () => ({ data: [{ id: 5, name: 'RWCA' }] }) }))
vi.mock('./crossProjectBoard', () => ({ useCrossProjectBoard: () => ({ columns: [], projectKeys: Object.keys(mocks.boards), boards: mocks.boards,
  cardConfigByProject: {}, isLoading: false, resolveStatus: () => null }) }))
vi.mock('./KanbanBoard', () => ({ KanbanBoard: ({ toolbarExtra }: { toolbarExtra?: ReactNode }) => <div>kanban board{toolbarExtra}</div> }))
vi.mock('@/features/tables/IssueTable', () => ({ IssueTable: ({ issues }: { issues: unknown[] }) => <div>task list of {issues.length}</div> }))
vi.mock('@/features/projects/CreateClientDialog', () => ({
  CreateClientDialog: ({ open }: { open: boolean }) => {
    mocks.settingsOpen = open
    return open ? <div>sub-workspace settings window</div> : null
  },
}))

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
  it('has Settings next to Summary, opening the sub-workspace settings without leaving the view (AFIT, 13 Nov 2026)', async () => {
    mocks.issues = [issue({})]
    renderAt('/projects/all-issues?team=4&client=5&view=summary')
    const tabs = within(screen.getByRole('tablist', { name: 'Views' })).getAllByRole('tab').map((t) => t.textContent)
    expect(tabs).toEqual(['Kanban', 'Tasks', 'Summary', 'Sub-workspaces', 'Goals', 'Members', 'Settings'])
    await userEvent.click(screen.getByRole('tab', { name: 'Settings' }))
    expect(screen.getByText('sub-workspace settings window')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Summary' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('where')).toHaveTextContent('view=summary')
  })

  it('has Create task on the board, filled in from the workspace and sub-workspace (AFIT, 16 Nov 2026)', async () => {
    renderAt('/projects/all-issues?team=4&client=5')
    await userEvent.click(screen.getByRole('button', { name: 'Create task' }))
    expect(useUiStore.getState().createIssueOpen).toBe(true)
    expect(useUiStore.getState().createIssueDefaults).toMatchObject({ teamId: 4, clientId: 5 })
  })

  it("brings a workspace's own tabs (sub-workspaces, goals, members) onto the board (AFIT, 20 Nov 2026)", async () => {
    renderAt('/projects/all-issues?team=4')
    await userEvent.click(screen.getByRole('tab', { name: 'Sub-workspaces' }))
    expect(screen.getByText('sub-workspaces of Team 4')).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('team=4&view=sub-workspaces')
    await userEvent.click(screen.getByRole('tab', { name: 'Goals' }))
    expect(screen.getByText('goals tab')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Members' }))
    expect(screen.getByText('members tab')).toBeInTheDocument()
  })

  it('has no workspace tabs until one workspace is picked', () => {
    renderAt('/projects/all-issues?view=members')
    const tabs = within(screen.getByRole('tablist', { name: 'Views' })).getAllByRole('tab').map((t) => t.textContent)
    expect(tabs).toEqual(['Kanban', 'Tasks', 'Summary'])
    expect(screen.getByRole('tab', { name: 'Kanban' })).toHaveAttribute('aria-selected', 'true')
  })

  it('offers Columns on the board to someone who can change a board in view', async () => {
    mocks.boards = { RWCA: { can_configure: false } }
    const { unmount } = renderAt('/projects/all-issues?team=4')
    expect(screen.queryByRole('button', { name: 'Columns' })).not.toBeInTheDocument()
    unmount()
    mocks.boards = { RWCA: { can_configure: true } }
    renderAt('/projects/all-issues?team=4')
    await userEvent.click(screen.getByRole('button', { name: 'Columns' }))
    expect(screen.getByText('columns window')).toBeInTheDocument()
    mocks.boards = {}
  })

  it('offers Settings only once a sub-workspace is chosen', () => {
    renderAt('/projects/all-issues?team=4')
    expect(screen.queryByRole('tab', { name: 'Settings' })).not.toBeInTheDocument()
  })

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
