import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { TimesheetBreakdownLink } from './TimesheetBreakdown'

const mocks = vi.hoisted(() => ({ params: null as unknown }))
vi.mock('@/api/timesheets', () => ({
  useTimeEntries: (params: unknown, enabled: boolean) => {
    if (enabled) mocks.params = params
    return {
      isLoading: false,
      data: enabled
        ? [
            { id: 1, user: { id: 2, display_name: 'Pat' }, work_date: '2026-11-03', duration_seconds: 2 * 3600, description: 'Bank recs', is_billable: true, is_running: false },
            { id: 2, user: { id: 3, display_name: 'Sam' }, work_date: '2026-11-04', duration_seconds: 5400, description: '', is_billable: false, is_running: false },
            { id: 3, user: { id: 2, display_name: 'Pat' }, work_date: '2026-11-05', duration_seconds: 3 * 3600, description: 'Accruals', is_billable: true, is_running: false },
          ]
        : undefined,
    }
  },
}))

describe('Timesheet breakup', () => {
  it('opens from the time on a card without opening the card, and shows who logged what', async () => {
    const openCard = vi.fn()
    render(
      <div onClick={openCard} role="article">
        <TimesheetBreakdownLink issueId={42} issueKey="RWCA-1" title="Smith FY26">
          6.5h / 10h
        </TimesheetBreakdownLink>
      </div>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Timesheet breakup for RWCA-1' }))
    expect(openCard).not.toHaveBeenCalled()
    expect(mocks.params).toEqual({ issue: 42, page_size: 500 })
    const dialog = screen.getByRole('dialog', { name: 'Timesheet breakup — RWCA-1' })
    expect(dialog).toHaveTextContent('6.5h logged by 2 people')
    const pat = within(dialog).getByRole('region', { name: 'Pat' })
    expect(pat).toHaveTextContent('Pat 5h')
    expect(within(pat).getAllByRole('row').map((r) => r.textContent)).toEqual(['Tue 3 Nov 20262hBank recs', 'Thu 5 Nov 20263hAccruals'])
    expect(within(dialog).getByRole('region', { name: 'Sam' })).toHaveTextContent('1.5hNo descriptionNon-billable')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
    expect(openCard).not.toHaveBeenCalled()
  })
})
