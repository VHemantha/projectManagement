import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuidePanel } from './GuidePanel'

const mocks = vi.hoisted(() => ({ state: undefined as unknown, run: vi.fn() }))

vi.mock('./StopRun', () => ({ StopRun: ({ runId }: { runId?: string }) => <button type="button">Stop {runId}</button> }))

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
    expect(loans).toHaveTextContent(/amount not found in the documents \(it may be calculated\)/)
    expect(screen.getByRole('button', { name: 'Write it again' })).toBeEnabled()
  })

  it('shows the eight sections, each event as what happened → why it matters → what to do, followed through', () => {
    const none = { flags: [] as string[] }
    mocks.state = {
      has_precheck: true, history: [],
      latest: { status: 'complete', guide: {
        format: 2, summary: '', words: 320, flags: [], evidence: GUIDE.evidence,
        decision: { state: 'guide', label: 'Preparation guide', reason: '2 significant events (1 to confirm); 1 priority risk; 1 open check.' },
        snapshot: { activities: 'Residential rental at 43 Te Wharo Drive.', assets_and_funding: 'One property, ASB loan.', records: 'ANZ export.',
                    bookkeeping: 'Bank exports only.', period: 'Year to 31 March 2026.', sources: [], ...none },
        events: [
          { id: 'E1', event: 'Property acquired at 12 Kowhai Rd.', status: 'confirmed', why_it_matters: 'A new rental asset and loan.',
            action: 'Check settlement, funding and GST.', effect: 'Fixed assets and borrowings up.', sources: [{ id: 'D1', label: 'Rates.pdf, page 1', evidence_id: 'E1' }],
            not_followed_through: [], ...none },
          { id: 'E2', event: 'Large payment to ASB.', status: 'suspected', why_it_matters: 'May be a loan settlement.', action: 'Confirm the loan balance.',
            effect: '', sources: [], flags: ['not_followed_through'], not_followed_through: ['checklist'] },
        ],
        prior_year: [{ item: 'Interest split wrongly last year.', kind: 'reviewer_point', follow_through: 'Apply the corrected split.', events: [], sources: [], ...none }],
        risks: [{ area: 'Loans', what_could_be_wrong: 'Loan balance misstated.', examine: 'ASB statements.', evidence: 'Annual loan summary.', events: ['E2'], sources: [], ...none }],
        sequence: [
          { step: 'Reconcile the ANZ account.', depends_on: 'nothing', can_start_now: true, escalate: '', events: [], sources: [], ...none },
          { step: 'Reconcile the ASB loan.', depends_on: 'Annual loan summary', can_start_now: false, escalate: 'If settled, tell the manager.', events: ['E2'], sources: [], ...none },
        ],
        judgments: [{ judgment: 'Allocate the purchase price.', evidence: 'Settlement statement.', manager_approval: true, reference: 'IR 264', events: ['E1'], sources: [], ...none }],
        queries: { manager: [], client: [{ question: 'What was the payment to ASB for?', events: ['E2'], ...none }],
                   outstanding: [{ item: 'Annual loan summary', events: [], ...none }] },
        checklist: [{ check: 'Property purchase recorded.', status: 'open', events: ['E1'], ...none }, { check: 'GST.', status: 'na', events: [], ...none }],
        roll_forward: [{ item: 'Revisit the purchase price allocation.', why: 'It recurs each year.', sources: [], ...none }],
      } },
    }
    render(<GuidePanel jobKey="SMITH-1" />)
    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(titles).toEqual(['1. Job snapshot', '2. Significant events and possible risk areas', '3. Prior-year findings and continuity', '4. Priority risks and material areas',
      '5. Starting sequence', '6. Judgments, assumptions and references', '7. Queries to be asked', '8. Completion and handover checklist'])
    expect(screen.getByRole('region', { name: 'Job snapshot' })).toHaveTextContent('FS preparation periodYear to 31 March 2026.')
    const property = screen.getByRole('article', { name: /E1 Property acquired/ })
    expect(property).toHaveTextContent('Confirmed')
    expect(property).toHaveTextContent('What happened Property acquired at 12 Kowhai Rd.')
    expect(property).toHaveTextContent('Why it matters A new rental asset and loan.')
    expect(property).toHaveTextContent('What to do Check settlement, funding and GST.')
    expect(property).toHaveTextContent('Effect on the figures Fixed assets and borrowings up.')
    expect(within(property).getByRole('link', { name: /Rates\.pdf/ })).toHaveAttribute('href', 'https://drive.example/r')
    const payment = screen.getByRole('article', { name: /E2 Large payment/ })
    expect(payment).toHaveTextContent('Suspected — to confirm')
    expect(payment).toHaveTextContent('Not followed through: no a checklist line')
    const sequence = screen.getByRole('region', { name: 'Starting sequence' })
    expect(sequence).toHaveTextContent('Can start now')
    expect(sequence).toHaveTextContent('Waits on: Annual loan summary')
    expect(sequence).toHaveTextContent('Escalate: If settled, tell the manager.')
    expect(screen.getByRole('region', { name: 'Judgments, assumptions and references' })).toHaveTextContent('Manager approval')
    const queries = screen.getByRole('region', { name: 'Queries to be asked' })
    expect(within(queries).queryByText('For the manager')).not.toBeInTheDocument() // an empty list is left out
    expect(queries).toHaveTextContent('What was the payment to ASB for?')
    const checklist = screen.getByRole('region', { name: 'Completion and handover checklist' })
    expect(checklist).toHaveTextContent('Open Property purchase recorded.')
    expect(checklist).toHaveTextContent('N/A GST.')
    expect(within(checklist).getByRole('list', { name: 'To roll forward to next year' })).toHaveTextContent('Revisit the purchase price allocation. — It recurs each year.')
  })

  it('while it is being written, it can be stopped', () => {
    mocks.state = { has_precheck: true, history: [], latest: { run_id: 'g1', status: 'running', guide: {} } }
    render(<GuidePanel jobKey="SMITH-1" />)
    expect(screen.getByRole('button', { name: /Writing the guide/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Stop g1' })).toBeInTheDocument()
  })
})
