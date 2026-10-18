import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { BudgetKpi } from './BudgetKpi'

const mocks = vi.hoisted(() => ({ calls: [] as unknown[][] }))

vi.mock('@/api/guide', () => ({
  usePersonKpi: (...args: unknown[]) => {
    mocks.calls.push(args)
    return {
      isLoading: false,
      isError: false,
      data: {
        person: { id: 7, display_name: 'Pat' },
        period: { from: '', to: '' },
        finished: { tasks: 4, within_budget: 3, over_budget: 1, pct_within_budget: 75, budgeted_hours: 20, actual_hours: 22.5, efficiency_pct: 89 },
        open: { tasks: 2, over_budget_already: 1 },
        tasks: [
          { key: 'SMITH-1', summary: 'Smith rental', project: 'SMITH', status: 'Done', done: true, budgeted_hours: 5, actual_hours: 8, variance_hours: 3, within_budget: false },
          { key: 'SMITH-2', summary: 'Smith GST', project: 'SMITH', status: 'Done', done: true, budgeted_hours: 5, actual_hours: 4, variance_hours: -1, within_budget: true },
        ],
      },
    }
  },
}))

describe('BudgetKpi', () => {
  it("shows the person's budget vs actual and the tasks over budget, for a chosen period", async () => {
    render(<MemoryRouter><BudgetKpi userId={7} /></MemoryRouter>)
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText('Finished within budget (3 of 4)')).toBeInTheDocument()
    expect(screen.getByText('22.5h / 20.0h')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SMITH-1' })).toHaveAttribute('href', '/projects/SMITH/issues/SMITH-1')
    expect(screen.queryByRole('link', { name: 'SMITH-2' })).not.toBeInTheDocument()
    const before = mocks.calls.length
    await userEvent.click(screen.getByRole('button', { name: '12 months' }))
    expect(screen.getByRole('button', { name: '12 months' })).toHaveAttribute('aria-pressed', 'true')
    expect(mocks.calls.length).toBeGreaterThan(before)
    expect(mocks.calls.at(-1)?.[0]).toBe(7)
  })
})
