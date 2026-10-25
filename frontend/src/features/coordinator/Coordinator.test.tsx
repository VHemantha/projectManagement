import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CoordinatorConsolePage } from './CoordinatorConsolePage'
import { LeavePage } from './LeavePage'
import { GlobalSidebar } from '@/app/GlobalSidebar'
import { TooltipProvider } from '@/design-system'
import { useAuthStore, type CurrentUser } from '@/store/authStore'

const mocks = vi.hoisted(() => ({
  updateSettings: vi.fn(),
  setPolicy: vi.fn(),
  requestLeave: vi.fn(),
  decide: vi.fn(),
  settings: { paused: false, shadow_mode: true, timezone: 'Pacific/Auckland', daily_cost_cap_usd: 5, updated_by: null, updated_at: '' },
}))

const mutation = (fn: unknown) => ({ mutate: fn, isPending: false, isError: false })

vi.mock('@/api/coordinator', () => ({
  useCoordinatorSettings: () => ({ data: mocks.settings }),
  useUpdateCoordinatorSettings: () => mutation(mocks.updateSettings),
  usePolicies: () => ({
    data: {
      rules: [{ key: 'hours_tolerance_pct', label: 'Hours: tolerance (% of budget)', default: 125, kind: 'number', help: 'Exactly this is within tolerance.',
                minimum: 100, maximum: 300, choices: [], current: 125 }],
      policies: [],
    },
  }),
  useSetPolicy: () => mutation(mocks.setPolicy),
  useLeave: () => ({ data: { leave: [{ id: 3, user: { id: 2, display_name: 'Pat' }, start_date: '2026-11-09', end_date: '2026-11-10', kind: 'annual',
    kind_label: 'Annual leave', hours_per_day: null, note: '', status: 'pending', status_label: 'Waiting for approval', decided_by: null,
    decided_at: null, created_at: '' }] }, isLoading: false }),
  useDecideLeave: () => mutation(mocks.decide),
  useRequestLeave: () => mutation(mocks.requestLeave),
  useWithdrawLeave: () => mutation(vi.fn()),
  useSchedules: () => ({ data: { schedules: [] } }),
  useSetSchedule: () => mutation(vi.fn()),
  useHolidays: () => ({ data: { holidays: [{ date: '2026-10-26', name: 'Labour Day' }] } }),
  useAddHoliday: () => mutation(vi.fn()),
  useRemoveHoliday: () => mutation(vi.fn()),
  useAgentActions: () => ({ data: { actions: [] } }),
  useCases: () => ({ data: { cases: [{ id: 1, issue: 'ABC-12', title: 'Client ABC year end', person: { id: 2, display_name: 'Pat' }, kind: 'prep_due',
    kind_label: 'Preparation due soon', state: 'answered', state_label: 'Answered', due_date: '2026-11-05', revised_due: '2026-11-06', asked: 1,
    last_asked_at: null, escalated_to: null, opened_at: '', closed_reason: '',
    commitment: { eta_date: '2026-11-06', remaining_hours: 8, cause: 'Bookkeeping errors', status: 'open' } }] } }),
  useAudit: () => ({ data: { entries: [] } }),
}))
vi.mock('@/app/ProjectSwitcher', () => ({ ProjectSwitcher: () => null }))

const user = (role: 'member' | 'ceo') =>
  ({ id: 1, email: 'x@example.com', username: 'x', display_name: 'X', job_title: '', avatar: null, is_staff: role === 'ceo', role }) as CurrentUser

describe('Coordinator console', () => {
  beforeEach(() => {
    mocks.updateSettings.mockClear()
    mocks.setPolicy.mockClear()
    mocks.decide.mockClear()
  })

  it('is the CEO’s alone', () => {
    useAuthStore.setState({ user: user('member') })
    render(<MemoryRouter><CoordinatorConsolePage /></MemoryRouter>)
    expect(screen.getByText(/Only the CEO can open the coordinator console/)).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('lets the CEO pause the agent, see shadow mode and change a rule', async () => {
    useAuthStore.setState({ user: user('ceo') })
    render(<MemoryRouter><CoordinatorConsolePage /></MemoryRouter>)
    expect(screen.getByRole('status')).toHaveTextContent('Shadow mode')
    await userEvent.click(screen.getByRole('checkbox', { name: /Emergency pause/ }))
    expect(mocks.updateSettings).toHaveBeenCalledWith({ paused: true })

    await userEvent.click(screen.getByRole('tab', { name: 'Rules' }))
    const rules = screen.getByRole('region', { name: 'Rules' })
    expect(rules).toHaveTextContent('Hours: tolerance (% of budget)')
    await userEvent.click(within(rules).getByRole('button', { name: 'Change' }))
    const input = within(rules).getByRole('spinbutton', { name: 'Hours: tolerance (% of budget)' })
    await userEvent.clear(input)
    await userEvent.type(input, '130')
    await userEvent.type(within(rules).getByRole('textbox', { name: 'Why' }), 'Busy season')
    await userEvent.click(within(rules).getByRole('button', { name: 'Save' }))
    expect(mocks.setPolicy).toHaveBeenCalledWith({ key: 'hours_tolerance_pct', value: 130, note: 'Busy season' }, expect.anything())

    await userEvent.click(screen.getByRole('tab', { name: 'Follow-ups' }))
    const followUps = screen.getByRole('region', { name: 'Follow-ups' })
    expect(followUps).toHaveTextContent('ABC-12')
    expect(followUps).toHaveTextContent('Said: 8h to go, finish 6 Nov — Bookkeeping errors')
    expect(followUps).toHaveTextContent('Revised 6 Nov')

    await userEvent.click(screen.getByRole('tab', { name: 'Leave' }))
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(mocks.decide).toHaveBeenCalledWith({ id: 3, status: 'approved' })
  })
})

describe('Leave page', () => {
  it('requests leave for a single day', async () => {
    render(<MemoryRouter><LeavePage /></MemoryRouter>)
    const form = screen.getByRole('region', { name: 'Request leave' })
    const first = within(form).getByLabelText('First day')
    await userEvent.type(first, '2026-11-09')
    await userEvent.click(within(form).getByRole('button', { name: 'Request' }))
    expect(mocks.requestLeave).toHaveBeenCalledWith(
      { start_date: '2026-11-09', end_date: '2026-11-09', kind: 'annual', hours_per_day: null, note: '' }, expect.anything())
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeInTheDocument()
  })
})

describe('Sidebar', () => {
  const sidebar = () =>
    render(<TooltipProvider><MemoryRouter><GlobalSidebar expanded onToggle={() => {}} drawerOpen={false} onCloseDrawer={() => {}} /></MemoryRouter></TooltipProvider>)

  it('gives everyone the coordinator and leave, and only the CEO the console', () => {
    useAuthStore.setState({ user: user('member') })
    const { unmount } = sidebar()
    expect(screen.getByRole('link', { name: 'Coordinator' })).toHaveAttribute('href', '/coordinator')
    expect(screen.getByRole('link', { name: 'Leave' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'CEO console' })).not.toBeInTheDocument()
    unmount()
    useAuthStore.setState({ user: user('ceo') })
    sidebar()
    expect(screen.getByRole('link', { name: 'CEO console' })).toHaveAttribute('href', '/coordinator/console')
  })
})
