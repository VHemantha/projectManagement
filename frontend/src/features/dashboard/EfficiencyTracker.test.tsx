import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { EfficiencyTracker } from './EfficiencyTracker'
import { MyWorkPage } from '@/features/board/MyWorkPage'
import { useAuthStore } from '@/store/authStore'

const day = (date: string, logged: number, extra = {}) => ({ date, expected: 7.5, logged, jobs: logged, idle: 0, administration: 0, training: 0,
  under: logged < 7.5, ...extra })

vi.mock('@/api/timesheets', () => ({
  useEfficiency: () => ({
    isLoading: false, isError: false,
    data: {
      user: { id: 1, name: 'Pat' }, target: 7.5,
      days: [day('2026-11-19', 8), day('2026-11-20', 6, { jobs: 4, training: 2 })],
      summary: { expected: 15, logged: 14, jobs: 12, non_job: 2, efficiency_pct: 93, on_jobs_pct: 86, days_under: 1, working_days: 2 },
      jobs: [{ key: 'SMITH-1', summary: 'Smith FY26', budget: 20, logged: 25, used_pct: 125 }],
    },
  }),
  useTeamEfficiency: () => ({
    data: { target: 7.5, days: 10, people: [{ user: { id: 2, name: 'Amy' }, last_day: day('2026-11-20', 3),
      summary: { expected: 75, logged: 40, jobs: 40, non_job: 0, efficiency_pct: 53, on_jobs_pct: 100, days_under: 6, working_days: 10 } }] },
  }),
}))
vi.mock('@/features/dashboard/CeoDashboard', () => ({ CeoDashboard: () => <div>the CEO overview</div> }))
vi.mock('@/features/dashboard/DashboardHomePage', () => ({ DashboardHomePage: () => <div>the dashboard</div> }))
vi.mock('recharts', async (orig) => ({ ...(await orig<typeof import('recharts')>()), ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
vi.mock('@/api/issues', () => ({ useIssues: () => ({ data: { results: [] }, isLoading: false }), useMoveIssue: () => ({ mutate: vi.fn() }) }))
vi.mock('@/features/board/crossProjectBoard', () => ({ useCrossProjectBoard: () => ({ columns: [], cardConfigByProject: {}, isLoading: false }) }))
vi.mock('@/features/board/KanbanBoard', () => ({ KanbanBoard: () => <div>my tasks board</div> }))

describe('The efficiency tracker (AFIT, 21 Nov 2026)', () => {
  it("shows each day's hours against 7.5, the days under, the jobs against budget and the people led", () => {
    render(<EfficiencyTracker team />)
    const tiles = screen.getByRole('region', { name: 'Efficiency tracker' })
    expect(tiles).toHaveTextContent('Hours logged14.0h of 15.0h expected')
    expect(tiles).toHaveTextContent('Efficiency93%')
    expect(tiles).toHaveTextContent('Days under 7.5h1 of 2')
    const byDay = screen.getByRole('table', { name: 'Hours by day' })
    const fri = within(byDay).getByRole('row', { name: /Fri 20 Nov/ })
    expect(fri).toHaveTextContent('6.00h7.50h4.00h2.00hUnder 7.5h')
    expect(within(byDay).getByRole('row', { name: /Thu 19 Nov/ })).not.toHaveTextContent('Under')
    expect(screen.getByRole('table', { name: 'My open jobs against budget' })).toHaveTextContent('SMITH-1 Smith FY2625.0h20h 125%')
    expect(screen.getByRole('table', { name: 'Team efficiency' })).toHaveTextContent('Amy40.0h75.0h 53%63.0h under')
  })

  it('is on the landing page beside the tasks and the dashboard', async () => {
    useAuthStore.setState({ user: { id: 1, role: 'member', display_name: 'Pat' } as never })
    render(<MemoryRouter><MyWorkPage /></MemoryRouter>)
    const tabs = within(screen.getByRole('tablist', { name: 'Home views' })).getAllByRole('tab').map((t) => t.textContent)
    expect(tabs).toEqual(['My tasks', 'Dashboard', 'Efficiency tracker'])
    expect(screen.getByText('my tasks board')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Dashboard' }))
    expect(screen.getByText('the dashboard')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Efficiency tracker' }))
    expect(screen.getByRole('region', { name: 'Efficiency tracker' })).toBeInTheDocument()
  })

  it("gives the CEO the overview and the team's efficiency", () => {
    useAuthStore.setState({ user: { id: 9, role: 'ceo', display_name: 'Dushan' } as never })
    render(<MemoryRouter><MyWorkPage /></MemoryRouter>)
    expect(within(screen.getByRole('tablist', { name: 'Home views' })).getAllByRole('tab').map((t) => t.textContent)).toEqual(['Overview', 'Efficiency tracker'])
    expect(screen.getByText('the CEO overview')).toBeInTheDocument()
  })
})
