import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuidePanel } from './GuidePanel'

const mocks = vi.hoisted(() => ({ state: undefined as unknown, run: vi.fn() }))

vi.mock('@/api/guide', () => ({
  useJobGuide: () => ({ data: mocks.state, isLoading: false, isError: false }),
  useRunGuide: () => ({ mutate: mocks.run, isPending: false, isError: false }),
}))

const GUIDE = {
  summary: 'Bank and rates first; the loan waits on the client.',
  decision: { state: 'guide', label: 'Preparation guide', reason: '2 steps; 1 waits on information from the client.' },
  evidence: { E1: { file_name: 'Rates.pdf', location: 'page 1', quote: 'Total 2,610.00', drive_url: 'https://drive.example/r' } },
  steps: [
    { area: 'Rates', step: 'Account for rates of 2,610.00 paid from the ANZ account.', check: 'Agree the total to the bank statement.',
      waits_on_client: false, sources: [{ id: 'D1', label: 'Rates.pdf, page 1', evidence_id: 'E1' }], flags: [] },
    { area: 'Loans', step: 'Record the ASB interest once the annual summary arrives.', check: '', waits_on_client: true, sources: [],
      flags: ['figure_not_in_documents'] },
  ],
}

describe('GuidePanel', () => {
  beforeEach(() => mocks.run.mockClear())

  it('writes the guide, suggesting the pre-check first when there is none', async () => {
    mocks.state = { has_precheck: false, latest: null, history: [] }
    render(<GuidePanel jobKey="SMITH-1" />)
    expect(screen.getByText(/Run the pre-check first/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Write the preparation guide' }))
    expect(mocks.run).toHaveBeenCalled()
  })

  it('shows the steps by area, with the check, what waits on the client and the evidence', () => {
    mocks.state = { has_precheck: true, history: [], latest: { status: 'complete', guide: GUIDE } }
    render(<GuidePanel jobKey="SMITH-1" />)
    expect(screen.getByText('2 steps; 1 waits on information from the client.')).toBeInTheDocument()
    const rates = screen.getByRole('region', { name: 'Rates' })
    expect(rates).toHaveTextContent('Account for rates of 2,610.00 paid from the ANZ account.')
    expect(rates).toHaveTextContent('Agree the total to the bank statement.')
    expect(within(rates).getByRole('link', { name: /Rates\.pdf, page 1/ })).toHaveAttribute('href', 'https://drive.example/r')
    const loans = screen.getByRole('region', { name: 'Loans' })
    expect(loans).toHaveTextContent('Waits on information from the client')
    expect(loans).toHaveTextContent(/figure not found in the documents/)
    expect(screen.getByRole('button', { name: 'Write it again' })).toBeEnabled()
  })
})
