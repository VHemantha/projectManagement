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

  it('shows the format-3 guide: cautions first, no events section, no questions, the steps as a flow chart, tables and charts (AFIT, 21 Nov 2026)', () => {
    const none = { flags: [] as string[] }
    const src = [{ id: 'D1', label: 'Rates.pdf, page 1', evidence_id: 'E1' }]
    mocks.state = {
      has_precheck: true, history: [],
      latest: { status: 'complete', guide: {
        format: 3, summary: '', words: 320, flags: [], evidence: GUIDE.evidence,
        decision: { state: 'guide', label: 'Preparation guide', reason: '2 areas of caution (1 high); 3 steps to finalisation; 1 judgment; 1 open check.' },
        cautions: [
          { area: 'Loan', caution: 'The ASB payment may have settled the loan.', level: 'high', sources: src, ...none },
          { area: 'Opening balances', caution: 'Agree them to last year before anything else.', level: 'low', sources: [], ...none },
        ],
        snapshot: { activities: 'Residential rental at 43 Te Wharo Drive.', assets_and_funding: 'One property, ASB loan.', records: 'ANZ export.',
                    bookkeeping: 'Bank exports only.', period: 'Year to 31 March 2026.', sources: [], ...none },
        events: [{ id: 'E1', event: 'Large payment to ASB.', status: 'suspected', why_it_matters: '', action: '', effect: '', sources: [], not_followed_through: [], ...none }],
        prior_year: [{ item: 'Interest split wrongly last year.', kind: 'reviewer_point', follow_through: 'Apply the corrected split.', events: [], sources: [], ...none }],
        risks: [{ area: 'Loans', what_could_be_wrong: 'Loan balance misstated.', examine: 'ASB statements.', evidence: 'Annual loan summary.', events: [], sources: [], ...none }],
        steps: [
          { n: 1, phase: 'reconcile', step: 'Reconcile the ANZ account.', depends_on: 'nothing', can_start_now: true, escalate: '', events: [], sources: src, ...none },
          { n: 2, phase: 'reconcile', step: 'Reconcile the ASB loan.', depends_on: 'Annual loan summary', can_start_now: false, escalate: 'If settled, tell the manager.',
            events: ['E1'], sources: [], ...none },
          { n: 3, phase: 'finalise', step: 'File the return.', depends_on: 'the steps before', can_start_now: false, escalate: '', events: [], sources: [], flags: ['added_by_code'] },
        ],
        judgments: [{ area: 'Fixed assets', judgment: 'Allocate the purchase price.', evidence: 'Settlement statement.', manager_approval: true, reference: 'IR 264',
          events: [], sources: [], ...none }],
        points: [{ kind: 'action', text: 'Agree the ASB payment to the loan statement.', events: ['E1'], sources: [], ...none }],
        outstanding: [{ group: 'ASB loan', item: 'Annual loan summary', flags: [] }],
        checklist: [{ check: 'Loan settlement confirmed.', status: 'open', events: ['E1'], ...none }, { check: 'GST.', status: 'na', events: [], ...none },
                    { check: 'Opening balances agreed.', status: 'done', events: [], ...none }],
        roll_forward: [{ item: 'Revisit the purchase price allocation.', why: 'It recurs each year.', sources: [], ...none }],
        phase_labels: { reconcile: 'Bank and reconciliations', finalise: 'Finalisation' },
      } },
    }
    render(<GuidePanel jobKey="SMITH-1" />)
    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent?.trim())
    expect(titles).toEqual(['Areas of caution', '1 Job snapshot', '2 Prior-year findings and continuity', '3 Priority risks and material areas',
      '4 Steps to finalisation', '5 Areas needing judgment', '6 Points to note', '7 Completion and handover checklist'])
    // No events section, and no questions anywhere.
    expect(screen.queryByText(/Significant events/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Queries/)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('?')
    // Cautions: a chart of the levels and a table, the highest first.
    const cautions = screen.getByRole('region', { name: 'Areas of caution' })
    expect(within(cautions).getByRole('img', { name: 'Areas of caution: 1 high, 0 medium, 1 low' })).toBeInTheDocument()
    expect(within(cautions).getAllByRole('row')[1]).toHaveTextContent('HighLoanThe ASB payment may have settled the loan.')
    expect(within(cautions).getByRole('link', { name: /Rates\.pdf/ })).toHaveAttribute('href', 'https://drive.example/r')
    // The snapshot is a table.
    expect(within(screen.getByRole('region', { name: 'Job snapshot' })).getByRole('row', { name: /FS preparation period/ })).toHaveTextContent('Year to 31 March 2026.')
    // The steps: a flow chart by phase, ending at finalisation, and a table.
    const steps = screen.getByRole('region', { name: 'Steps to finalisation' })
    const flow = within(steps).getByRole('figure', { name: 'Flow chart of the steps to finalisation' })
    expect(flow).toHaveTextContent('3 steps in 2 phases: 1 can start now, 2 wait on something')
    expect(flow).toHaveTextContent('1 Bank and reconciliations')
    expect(flow).toHaveTextContent('2 Finalisation')
    expect(flow).toHaveTextContent('Reconcile the ASB loan. — waits on Annual loan summary')
    const row = within(steps).getByRole('row', { name: /Reconcile the ASB loan/ })
    expect(row).toHaveTextContent('Escalate: If settled, tell the manager.')
    expect(row).toHaveTextContent('Waits')
    // Judgment areas, points and the documents still to come, as tables.
    expect(within(screen.getByRole('region', { name: 'Areas needing judgment' })).getByRole('row', { name: /Fixed assets/ }))
      .toHaveTextContent('Allocate the purchase price.Settlement statement.IR 264Needed')
    const points = screen.getByRole('region', { name: 'Points to note' })
    expect(points).toHaveTextContent('ActionAgree the ASB payment to the loan statement.')
    expect(within(points).getByRole('table', { name: /Still to come from the client/ })).toHaveTextContent('ASB loanAnnual loan summary')
    // The checklist's progress as a chart, then the table and the roll-forward.
    const checklist = screen.getByRole('region', { name: 'Completion and handover checklist' })
    expect(within(checklist).getByRole('img', { name: 'Checklist: 1 done, 1 open, 1 not applicable' })).toBeInTheDocument()
    expect(checklist).toHaveTextContent('33% done')
    expect(within(checklist).getByRole('table', { name: 'To roll forward to next year' })).toHaveTextContent('Revisit the purchase price allocation.It recurs each year.')
  })

  it('shows an eight-section guide the new way: no events section and none of its questions', () => {
    const none = { flags: [] as string[] }
    mocks.state = {
      has_precheck: true, history: [],
      latest: { status: 'complete', guide: {
        format: 2, summary: '', words: 100, flags: [], evidence: {},
        decision: { state: 'guide', label: 'Preparation guide', reason: '1 significant event; 0 priority risks; 0 open checks.' },
        snapshot: { activities: 'Rental.', assets_and_funding: '', records: '', bookkeeping: '', period: 'Year to 31 March 2026.', sources: [], ...none },
        events: [{ id: 'E1', event: 'Large payment to ASB.', status: 'suspected', why_it_matters: '', action: '', effect: '', sources: [], not_followed_through: [], ...none }],
        prior_year: [], risks: [], judgments: [], checklist: [], roll_forward: [],
        sequence: [{ step: 'Reconcile the ANZ account.', depends_on: 'nothing', can_start_now: true, escalate: '', events: [], sources: [], ...none }],
        queries: { manager: [], client: [{ question: 'What was the payment to ASB for?', events: ['E1'], ...none }],
                   outstanding: [{ item: 'Annual loan summary', events: [], ...none }] },
      } },
    }
    render(<GuidePanel jobKey="SMITH-1" />)
    expect(screen.getByText(/Written before 21 Nov 2026/)).toBeInTheDocument()
    expect(screen.queryByText('Large payment to ASB.')).not.toBeInTheDocument()
    expect(screen.queryByText('What was the payment to ASB for?')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Steps to finalisation' })).toHaveTextContent('Reconcile the ANZ account.')
    expect(screen.getByRole('region', { name: 'Points to note' })).toHaveTextContent('Annual loan summary')
  })

  it('while it is being written, it can be stopped', () => {
    mocks.state = { has_precheck: true, history: [], latest: { run_id: 'g1', status: 'running', guide: {} } }
    render(<GuidePanel jobKey="SMITH-1" />)
    expect(screen.getByRole('button', { name: /Writing the guide/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Stop g1' })).toBeInTheDocument()
  })
})
