import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { LogTimeModal } from './LogTimeModal'

const mocks = vi.hoisted(() => ({ create: vi.fn(), people: [] as { id: number; display_name: string }[] }))

vi.mock('@/api/timesheets', () => ({
  useCreateTimeEntry: () => ({ mutate: mocks.create, isPending: false, error: null }),
  useUpdateTimeEntry: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useOnBehalfPeople: () => ({ data: mocks.people }),
}))
vi.mock('@/api/issues', () => ({ useIssues: () => ({ data: undefined }) }))

describe('Log time for someone else (AFIT, 1 Nov 2026)', () => {
  it('lets a lead tick the box, pick the person and log the time for them', async () => {
    mocks.people = [{ id: 7, display_name: 'Amy' }]
    render(<LogTimeModal open onOpenChange={vi.fn()} defaultDate="2026-11-01" />)
    await userEvent.click(screen.getByRole('checkbox', { name: /Log for someone else/ }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Person' }), '7')
    await userEvent.type(screen.getByLabelText('Hours'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ user_id: 7, hours: 2, work_date: '2026-11-01' }), expect.anything())
  })

  it('offers no tick to someone who leads nobody, and logs their own time', async () => {
    mocks.people = []
    mocks.create.mockClear()
    render(<LogTimeModal open onOpenChange={vi.fn()} defaultDate="2026-11-01" />)
    expect(screen.queryByRole('checkbox', { name: /Log for someone else/ })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Hours'), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.create.mock.calls[0][0]).not.toHaveProperty('user_id')
  })
})
