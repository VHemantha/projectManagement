import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { CeoDashboard } from '@/api/reports'
import { MyWorkPage } from '@/features/board/MyWorkPage'

// Stable objects: a new list on every render would re-render the board forever.
const mocks = vi.hoisted(() => ({
  role: 'ceo' as 'ceo' | 'member',
  page: { results: [] },
  board: { columns: [], cardConfigByProject: {}, isLoading: false, resolveStatus: () => null },
  users: { ceo: { user: { id: 1, role: 'ceo' } }, member: { user: { id: 2, role: 'member' } } },
}))

const DATA: CeoDashboard = {
  as_of: '2026-10-28T09:00:00Z',
  totals: { open: 24, overdue: 3, due_this_week: 5, completed_30_days: 11, hours_this_month: 182.5, timesheets_to_approve: 2 },
  stages: [{ stage: 'To Start', tasks: 9 }, { stage: 'In Progress', tasks: 12 }],
  workspaces: [{ workspace: 'Team 1', open: 20, overdue: 3, on_time: 17, completed_30: 9 }],
  sub_workspaces: [{ sub_workspace: 'RWCA', open: 14 }],
  workload: [{ person: 'Pat', open: 8, overdue: 2, on_time: 6 }],
  priorities: [{ priority: 'High', tasks: 4 }],
  flow: [{ week: '2026-10-19', created: 6, completed: 4 }],
  hours: [{ week: '2026-10-19', billable: 70, non_billable: 8 }],
  over_budget: [{ key: 'RWCA-7', summary: 'Smith FY26', budgeted: 8, actual: 11.5, team_lead: 'Pat' }],
  prechecks: [{ result: 'Ready for review', runs: 3 }],
  follow_ups: { waiting: 4, answered: 1, escalated: 1 },
  commitments_90_days: { kept: 3, missed: 1 },
  on_leave_today: ['Sam'],
}

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector(mocks.users[mocks.role]),
}))
vi.mock('@/api/reports', () => ({ useCeoDashboard: () => ({ data: DATA, isLoading: false, isError: false }) }))
vi.mock('@/api/issues', () => ({
  useIssues: () => ({ data: mocks.page, isLoading: false }),
  useMoveIssue: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/features/board/crossProjectBoard', () => ({
  useCrossProjectBoard: () => mocks.board,
}))
vi.mock('@/store/uiStore', () => ({ useUiStore: (selector: (s: unknown) => unknown) => selector({ openCreateIssue: vi.fn() }) }))

const renderHome = () => render(<MemoryRouter><MyWorkPage /></MemoryRouter>)

describe('CEO home page (AFIT, 28 Oct 2026)', () => {
  it('shows the organisation overview instead of "assigned to you"', () => {
    mocks.role = 'ceo'
    renderHome()
    expect(screen.getByRole('heading', { name: 'Organisation overview' })).toBeInTheDocument()
    expect(screen.queryByText(/Nothing assigned to you/)).not.toBeInTheDocument()
    expect(screen.getByText('Open tasks').parentElement).toHaveTextContent('24')
    expect(screen.getByText('Overdue').parentElement).toHaveTextContent('3')
    expect(screen.getByText('Hours logged this month').parentElement).toHaveTextContent('182.5h')
    expect(screen.getByRole('region', { name: 'Over budget' })).toHaveTextContent('RWCA-7Smith FY26Pat8h11.5h3.5h')
    expect(screen.getByRole('region', { name: 'Coordinator follow-ups' })).toHaveTextContent('75%')
    expect(screen.getByText(/On leave today/).parentElement).toHaveTextContent('Sam')
  })

  it('every chart can be read as a table', async () => {
    mocks.role = 'ceo'
    renderHome()
    const card = screen.getByRole('region', { name: 'Team Lead workload' })
    await userEvent.click(within(card).getByRole('button', { name: 'Table' }))
    expect(within(card).getByRole('table')).toHaveTextContent('Pat82')
  })

  it('everyone else still sees the tasks assigned to them', () => {
    mocks.role = 'member'
    renderHome()
    expect(screen.queryByText('Organisation overview')).not.toBeInTheDocument()
  })
})
