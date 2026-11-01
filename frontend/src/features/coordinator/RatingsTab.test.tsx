import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { RatingsTab } from './RatingsTab'
import type { Ratings } from '@/api/coordinator'

const mocks = vi.hoisted(() => ({ days: [] as unknown[] }))

const metric = (key: string, label: string, score: number | null, n: number, counted = true) => ({
  key, label, score, n, detail: `${n} items`, weight: 10, counted, note: counted ? '' : 'Not counted: fewer than 3 to go on',
})

const DATA: Ratings = {
  period: { from: '2026-08-03', to: '2026-10-31' },
  formula: {
    weights: [{ key: 'on_time', label: 'Tasks finished by their due date', weight: 25 }, { key: 'response', label: 'Follow-ups answered', weight: 10 }],
    bands: [{ from: 85, label: 'Excellent' }, { from: 70, label: 'Good' }, { from: 55, label: 'Needs improvement' }, { from: 0, label: 'At risk' }],
    min_items: 3,
    min_coverage_pct: 50,
  },
  people: [
    {
      person: { id: 2, display_name: 'Pat' }, period: { from: '2026-08-03', to: '2026-10-31' }, score: 62.5, rating: 'Needs improvement',
      metrics: [metric('on_time', 'Tasks finished by their due date', 60, 10), metric('response', 'Follow-ups answered', null, 1, false)],
      reasons: { 'Waiting for client documents': 3 }, finished_tasks: 10, previous_score: 58,
      history: [{ date: '2026-10-26', score: 58 }],
    },
  ],
}

vi.mock('@/api/coordinator', () => ({
  useRatings: (days?: number) => {
    mocks.days.push(days)
    return { data: DATA, isLoading: false, isError: false }
  },
}))

describe('Ratings (AFIT, 31 Oct 2026)', () => {
  it('explains the formula and shows each person with their KPIs, change and reasons', async () => {
    render(<RatingsTab />)
    const formula = screen.getByRole('region', { name: 'How the rating is worked out' })
    expect(formula).toHaveTextContent('Σ (weight × KPI) ÷ Σ weight')
    expect(formula).toHaveTextContent('Tasks finished by their due date: 25 (71%)')
    expect(formula).toHaveTextContent('Excellent 85+ · Good 70+ · Needs improvement 55+ · At risk below 55')
    const row = screen.getByRole('button', { name: 'Pat' }).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('62.5')
    expect(row).toHaveTextContent('Needs improvement')
    expect(row).toHaveTextContent('Up 4.5 since last week')
    expect(row).toHaveTextContent('Waiting for client documents: 3')
    await userEvent.click(screen.getByRole('button', { name: 'Pat' }))
    const kpis = screen.getByRole('list', { name: "Pat's KPIs" })
    expect(within(kpis).getAllByRole('listitem')[1]).toHaveTextContent('Not counted: fewer than 3 to go on')
    expect(screen.getByText(/Weekly ratings: 26 Oct 58/)).toBeInTheDocument()
  })

  it('looks back over another period', async () => {
    render(<RatingsTab />)
    await userEvent.selectOptions(screen.getByLabelText('Period'), '30')
    expect(mocks.days.at(-1)).toBe(30)
  })
})
