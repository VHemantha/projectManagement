import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { addDays, format } from 'date-fns'
import { describe, expect, it, vi } from 'vitest'

import { completionLabel } from '@/lib/plans'
import { MorningPlansPage } from './MorningPlansPage'

const today = format(new Date(), 'yyyy-MM-dd')
const tomorrow = addDays(new Date(), 1)
const user = (id: number, name: string) => ({ id, display_name: name, avatar: null })
const goal = (over: Record<string, unknown>) => ({
  id: 1, user: user(2, 'Amy'), date: today, text: 'ABC Ltd Preparation', linked_issue: null, sub_workspace: 'ABC Ltd',
  planned_hours: 7, complete_by: format(tomorrow, 'yyyy-MM-dd'), task_done: null, status: 'achieved', note: '', order: 0,
  carried_over_from: null, lead_check: '', checked_by: null, checked_at: null, created_at: '', updated_at: '', ...over,
})

const mocks = vi.hoisted(() => ({ check: vi.fn() }))
vi.mock('@/api/dailyGoals', () => ({
  useTeamPlans: () => ({
    isLoading: false,
    isError: false,
    data: {
      date: today,
      people: [
        { person: user(2, 'Amy'), planned_hours: 9, logged_hours: 6.5, achieved: 1, not_achieved: 0, unchecked: 1,
          goals: [goal({}), goal({ id: 2, text: 'Xyz Ltd Adjustments', planned_hours: 2, complete_by: today, status: 'planned' })] },
        { person: user(3, 'Oz'), planned_hours: 0, logged_hours: 0, achieved: 0, not_achieved: 0, unchecked: 0, goals: [] },
      ],
    },
  }),
  useCheckGoal: () => ({ mutate: mocks.check, isPending: false }),
  useDailyGoalsRange: () => ({ data: [] }),
  useCreateDailyGoal: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateDailyGoal: () => ({ mutate: vi.fn() }),
  useCarryOverGoal: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/api/issues', () => ({ useIssues: () => ({ data: undefined }) }))
vi.mock('@/store/uiStore', () => ({ useUiStore: (sel: (s: { openIssueModal: () => void }) => unknown) => sel({ openIssueModal: vi.fn() }) }))
vi.mock('@/design-system', async (orig) => ({ ...(await orig<object>()), Avatar: () => null }))

describe('Morning plans (AFIT, 1 Nov 2026)', () => {
  it('reads like the plan: hours today and the completion day', () => {
    expect(completionLabel('2026-11-02', '2026-11-01')).toBe('completion tomorrow (2 Nov 26)')
    expect(completionLabel('2026-11-01', '2026-11-01')).toBe('completion today (1 Nov 26)')
    expect(completionLabel('2026-11-04', '2026-11-01')).toBe('completion Wed 4 Nov 26')
  })

  it("shows the team lead everyone's plan with hours, what is done and not, and takes their check", async () => {
    render(<MorningPlansPage />)
    const amy = screen.getByRole('region', { name: 'Amy' })
    expect(amy).toHaveTextContent('9 hrs planned')
    expect(amy).toHaveTextContent('6.5 hrs logged')
    expect(amy).toHaveTextContent('1 to check')
    expect(amy).toHaveTextContent(`7 hrs today · completion tomorrow (${format(tomorrow, 'd MMM yy')})`)
    expect(amy).toHaveTextContent('2 hrs today · completion today')
    expect(screen.getByRole('region', { name: 'Oz' })).toHaveTextContent('No plan set')

    const first = within(amy).getByRole('group', { name: 'Check: ABC Ltd Preparation' })
    await userEvent.click(within(first).getByRole('button', { name: /Not done/ }))
    expect(mocks.check).toHaveBeenCalledWith({ id: 1, result: 'not_done' })
    expect(screen.getByRole('group', { name: 'Add to the plan' })).toBeInTheDocument()
  })
})
