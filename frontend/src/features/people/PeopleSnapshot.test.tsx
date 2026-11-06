import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { PeopleSnapshotRow, PersonDashboard } from '@/api/reports'
import { PersonSnapshotPage } from './PersonSnapshotPage'
import { TeamSnapshotPage } from './TeamSnapshotPage'

const mocks = vi.hoisted(() => ({ role: 'ceo', openIssueModal: vi.fn() }))

const person = (id: number, name: string) => ({ id, display_name: name, job_title: 'Accountant', avatar: null, role: 'member' })
const figures = { open: 0, in_progress: 0, to_start: 0, overdue: 0, due_this_week: 0, completed_week: 0, completed_30_days: 0 }

const PEOPLE: PeopleSnapshotRow[] = [
  { person: person(2, 'Amy'), ...figures, open: 3, in_progress: 2, overdue: 1, completed_30_days: 4, hours_today: 3, hours_week: 12,
    doing_now: { key: 'ABC-12', summary: 'Preparation', sub_workspace: 'ABC Ltd', since: '2026-11-05T09:30:00+13:00' }, on_leave: false,
    rating: { score: 82, rating: 'Strong', period_end: '2026-11-01' } },
  { person: person(3, 'Ben'), ...figures, open: 5, hours_today: 0, hours_week: 2, doing_now: null, on_leave: true, rating: null },
]

const AMY: PersonDashboard = {
  as_of: '2026-11-05T10:00:00+13:00',
  person: person(2, 'Amy'),
  on_leave: false,
  doing_now: PEOPLE[0].doing_now,
  figures: { ...figures, open: 3, in_progress: 2, overdue: 1, completed_week: 1, completed_30_days: 4 },
  hours: { today: 3, logged: 12, expected: 40, month: 30, by_day: [{ day: '2026-11-05', hours: 3, expected: 8 }] },
  stages: [{ stage: 'In Progress', tasks: 2 }, { stage: 'To Start', tasks: 1 }],
  open_jobs: [
    { key: 'ABC-12', summary: 'Preparation', sub_workspace: 'ABC Ltd', stage: 'In Progress', category: 'in_progress', priority: 'medium',
      start_date: null, due_date: '2026-11-03', days_overdue: 2, budget_hours: 10, actual_hours: 12, roles: ['Accountant'], completed_at: null },
  ],
  completed: [
    { key: 'XYZ-3', summary: 'Year end', sub_workspace: 'Xyz Ltd', stage: 'Complete', category: 'done', priority: 'medium',
      start_date: null, due_date: null, days_overdue: null, budget_hours: null, actual_hours: 5, roles: ['Accountant'], completed_at: '2026-11-04T10:00:00+13:00' },
  ],
  morning_plan: [{ text: 'ABC Ltd Preparation', key: 'ABC-12', planned_hours: 7, complete_by: '2026-11-06', status: 'in_progress',
    status_label: 'In progress', lead_check: '', note: '' }],
  recent_time: [],
  follow_ups: [{ key: 'ABC-12', summary: 'Preparation', matter: 'Preparation overdue', state: 'asked', state_label: 'Asked, waiting for a reply',
    due_date: '2026-11-03', revised_due: null, asked: 1 }],
  rating: null,
}

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector({ user: { id: 1, role: mocks.role } }),
}))
vi.mock('@/store/uiStore', () => ({
  useUiStore: (selector: (s: unknown) => unknown) => selector({ openIssueModal: mocks.openIssueModal }),
}))
vi.mock('@/api/reports', () => ({
  usePeopleSnapshot: () => ({ data: { as_of: '2026-11-05T10:00:00+13:00', people: PEOPLE }, isLoading: false, isError: false }),
  usePersonDashboard: () => ({ data: AMY, isLoading: false, isError: false }),
}))
// Charts need a measured box; jsdom has none.
vi.mock('recharts', async (orig) => {
  const actual = await orig<typeof import('recharts')>()
  return { ...actual, ResponsiveContainer: () => null }
})

describe("The CEO's team snapshot (AFIT, 5 Nov 2026)", () => {
  it('shows each person: what they are doing now and their figures, most overdue first', async () => {
    render(<MemoryRouter><TeamSnapshotPage /></MemoryRouter>)
    const cards = screen.getAllByRole('link', { name: /open their work/ })
    expect(cards.map((c) => c.getAttribute('aria-label'))).toEqual(['Amy: open their work', 'Ben: open their work'])
    expect(cards[0]).toHaveTextContent('Working on ABC-12 ABC Ltd · Preparation')
    expect(cards[0]).toHaveTextContent('Strong')
    expect(cards[0]).toHaveAttribute('href', '/people/work/2')
    expect(cards[1]).toHaveTextContent('No timer running')
    expect(cards[1]).toHaveTextContent('On leave')
    expect(screen.getByText(/1 of 2 working on something now/)).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByRole('combobox'), 'open')
    expect(screen.getAllByRole('link', { name: /open their work/ })[0]).toHaveAccessibleName('Ben: open their work')
    await userEvent.type(screen.getByRole('textbox', { name: 'Find a person' }), 'amy')
    expect(screen.getAllByRole('link', { name: /open their work/ })).toHaveLength(1)
  })

  it("shows one person's work in detail", async () => {
    render(
      <MemoryRouter initialEntries={['/people/work/2']}>
        <Routes>
          <Route path="/people/work/:userId" element={<PersonSnapshotPage />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Amy' })).toBeInTheDocument()
    const jobs = screen.getByRole('region', { name: 'Open jobs' })
    const row = within(jobs).getAllByRole('row')[1]
    expect(row).toHaveTextContent('ABC Ltd · Preparation')
    expect(row).toHaveTextContent('03-11-26')
    expect(row).toHaveTextContent('12 / 10')
    await userEvent.click(within(row).getByRole('button'))
    expect(mocks.openIssueModal).toHaveBeenCalledWith('ABC-12')
    expect(screen.getByRole('region', { name: "Today's morning plan" })).toHaveTextContent('7h today')
    expect(screen.getByRole('region', { name: 'Completed, last 30 days' })).toHaveTextContent('Year end')
    expect(screen.getByRole('region', { name: 'Coordinator follow-ups open' })).toHaveTextContent('Preparation overdue')
    expect(screen.getByText('12h')).toBeInTheDocument()
  })

  it('is for the CEO only', () => {
    mocks.role = 'member'
    render(<MemoryRouter><TeamSnapshotPage /></MemoryRouter>)
    expect(screen.getByText(/Only the CEO can see/)).toBeInTheDocument()
    mocks.role = 'ceo'
  })
})
