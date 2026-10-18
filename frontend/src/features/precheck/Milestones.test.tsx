import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { format } from 'date-fns'
import { describe, expect, it, vi } from 'vitest'

import { Milestones } from './Milestones'

const mocks = vi.hoisted(() => ({ stamp: vi.fn((_v: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()) }))

vi.mock('@/api/guide', () => ({
  useMilestones: () => ({
    data: {
      milestones: [
        { id: 1, kind: 'precheck', label: 'Pre-check', on: '2026-10-01', note: '', auto: true, by: 'Pat' },
        { id: 2, kind: 'checks', label: 'Checks', on: '2026-10-03', note: 'Bank agreed', auto: false, by: 'Sam' },
      ],
    },
  }),
  useStampMilestone: () => ({ mutate: mocks.stamp, isPending: false, isError: false }),
}))

describe('Milestones', () => {
  it('lists the dated stages and lets a person stamp one with a note', async () => {
    render(<Milestones jobKey="SMITH-1" />)
    const items = within(screen.getByRole('list', { name: 'Milestones' })).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('1 Oct 2026Pre-checkby the AI, run by Pat')
    expect(items[1]).toHaveTextContent('3 Oct 2026ChecksSam — Bank agreed')

    await userEvent.click(screen.getByRole('button', { name: 'Adjustments done' }))
    await userEvent.type(screen.getByLabelText('Note (optional)'), 'Depreciation posted')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.stamp).toHaveBeenCalledWith(
      { kind: 'adjustments', on: format(new Date(), 'yyyy-MM-dd'), note: 'Depreciation posted' }, expect.anything())
    expect(screen.getByRole('button', { name: 'Checks done' })).toBeInTheDocument()
  })
})
