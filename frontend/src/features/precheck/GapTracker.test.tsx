import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GapChip, GapTracker } from './GapTracker'

const mocks = vi.hoisted(() => ({ gaps: undefined as unknown, action: vi.fn() }))
vi.mock('@/api/precheck', () => ({
  useJobGaps: () => ({ data: mocks.gaps }),
  useGapAction: () => ({ mutate: mocks.action, isPending: false, isError: false, isSuccess: false }),
}))

const gap = (item: string, status: string) => ({ gap_id: item, group: 'G', item, status, label: status, still_needed: '', origin: 'precheck', evidence: [] })

describe('The provisional "not found" list (AFIT, 12 Nov 2026)', () => {
  beforeEach(() => mocks.action.mockReset())

  it('says it is provisional, counts each status, and lets a person check again or settle it', async () => {
    mocks.gaps = { provisional: true, finalized_at: null, updated_at: null, counts: { OPEN: 2, RESOLVED: 1, PARTIALLY_RESOLVED: 1 },
                   gaps: [gap('Income', 'RESOLVED'), gap('ANZ', 'OPEN'), gap('IRD', 'OPEN'), gap('Statements', 'PARTIALLY_RESOLVED')] }
    render(<GapTracker jobKey="SMITH-1" />)
    const region = screen.getByRole('region', { name: 'Items the AI keeps checking' })
    expect(region).toHaveTextContent('Provisional. The AI keeps checking every document, and new ones as they arrive, against 3 items')
    expect(region).toHaveTextContent('1 found')
    expect(region).toHaveTextContent('2 not found yet')
    expect(region).toHaveTextContent('1 partly found')
    await userEvent.click(screen.getByRole('button', { name: /Check again now/ }))
    expect(mocks.action).toHaveBeenCalledWith('recheck')
    await userEvent.click(screen.getByRole('button', { name: "Confirm what's still not found" }))
    expect(mocks.action).toHaveBeenCalledWith('finalize')
  })

  it('once settled, says so and offers nothing more to do', () => {
    mocks.gaps = { provisional: false, finalized_at: '2026-11-15T03:00:00+00:00', updated_at: null, counts: { CONFIRMED_MISSING: 1 },
                   gaps: [gap('IRD', 'CONFIRMED_MISSING')] }
    render(<GapTracker jobKey="SMITH-1" />)
    expect(screen.getByRole('region', { name: 'Items the AI keeps checking' })).toHaveTextContent('Settled on 15 Nov 2026. Every document was checked.')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows nothing before a pre-check has run', () => {
    mocks.gaps = undefined
    const { container } = render(<GapTracker jobKey="SMITH-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it("labels an item's status in plain words", () => {
    render(<GapChip status="OPEN" />)
    expect(screen.getByText('Not found yet — still checking')).toBeInTheDocument()
  })
})
