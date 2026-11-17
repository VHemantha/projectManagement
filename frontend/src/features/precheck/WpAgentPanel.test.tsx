import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { WpAgentPanel } from './WpAgentPanel'

const mocks = vi.hoisted(() => ({ state: undefined as unknown, run: vi.fn(), download: vi.fn(async () => {}), agents: [] as string[], save: vi.fn() }))

vi.mock('@/api/wpAgent', () => ({
  useWpAgent: (_key: string, agent = 'gst') => {
    mocks.agents.push(agent)
    return { data: mocks.state, isLoading: false, isError: false }
  },
  useRunWpAgent: (_key: string, agent = 'gst') => ({ mutate: (o: object) => mocks.run({ ...o, agent }), isPending: false, isError: false }),
  downloadWorkpaper: mocks.download,
  useSaveWorkpaper: () => ({ mutate: mocks.save, isPending: false, isError: false, data: undefined }),
}))
vi.mock('./StopRun', () => ({ StopRun: () => null }))

const SETUP = { entity: 'Acme Trading Ltd', ird_number: '123-456-789', fy_start: '2025-04-01', balance_date: '2026-03-31', basis: 'payments',
                frequency: 'two_monthly', software: 'Xero', currency: 'NZD', gl_version: '', gst_accounts: '', first_year: false, tolerance: '0' }
const PAUSE = 'Please re-upload the ageing report with the GST column\n\nThe uploaded Accounts Payable ageing report does not include the GST ' +
  'attributable to outstanding balances.\n\nIn Xero, enable the GST column in the report\'s column settings, then export and upload the report again.'

function run(gst: object, status = 'complete') {
  return {
    run_id: 'r1', kind: 'gst', status, verdict: 'not_ready', summary: '', coverage: { addressed: 0, total: 0 }, counts: {}, created_at: '2026-11-08T09:00:00Z',
    finished_at: '2026-11-08T09:02:00Z', requested_by: 'Pat', demo: false, progress: [], failure_reason: '', has_workpaper: true,
    options: { drive_link: 'https://drive.google.com/drive/folders/abc', ar_link: '', ap_link: '', setup: SETUP, choices: {} }, gst,
  }
}

const BRIDGE = { A: '2500.00', A_current: '2000.00', A_prior: '500.00', B: '450.00', C: '225.00', D: '-150.00', E: '2575.00', reported: '4475.00',
                 corrections: '-1900.00', F: '2575.00', unexplained: '0.00', tolerance: '0.00' }

describe('WP Agent panel (AFIT, 8 Nov 2026)', () => {
  beforeEach(() => {
    mocks.run.mockClear()
    mocks.state = { latest: null, history: [], defaults: { drive_link: '', ar_link: '', ap_link: '', choices: {}, setup: { ...SETUP, entity: 'Acme' } } }
  })

  it('takes the Drive link and the job settings, then runs', async () => {
    render(<WpAgentPanel jobKey="ACME-1" />)
    const form = screen.getByRole('form', { name: 'WP Agent inputs' })
    const button = within(form).getByRole('button', { name: 'Run reconciliation' })
    expect(button).toBeDisabled()
    await userEvent.type(within(form).getByLabelText(/Google Drive link/), 'https://drive.google.com/drive/folders/1AbC')
    await userEvent.selectOptions(within(form).getByLabelText('GST basis'), 'hybrid')
    await userEvent.click(within(form).getByLabelText(/First-year entity/))
    await userEvent.click(button)
    expect(mocks.run).toHaveBeenCalledWith(expect.objectContaining({
      drive_link: 'https://drive.google.com/drive/folders/1AbC', setup: expect.objectContaining({ basis: 'hybrid', first_year: true, entity: 'Acme' }),
    }))
  })

  it('shows the bridge, the exceptions and the corrections, and downloads the workpaper', async () => {
    mocks.state = {
      latest: run({
        status: 'Reconciled subject to corrections', summary: 'Reconciled subject to corrections.', bridge: BRIDGE, paused: {},
        exceptions: [{ id: 'X1', code: 'no_journals', severity: 'review', text: 'No journal report.', next_evidence: 'The journal report.', refs: [], amount: null }],
        corrections: [{ id: 'P1', title: 'GST payment debited to income tax', gst_effect: '-1900.00', explanation: 'IRD shows a GST payment.', evidence: [],
                        status: 'proposed — not posted', lines: [{ account: 'GST', debit: '1900.00', credit: '0.00' }, { account: 'Income Tax', debit: '0.00', credit: '1900.00' }] }],
        adjustments: [{ id: 'ADJ-1', category: 'Expenses not claimed', direction: 'input', effect: '-150.00', status: 'journal and late claim: one adjustment',
                        review: false, journals: ['J-1'], late_claims: ['LC-1'], subsequent_return: '2026-05-31', unmatched: null, description: '' }],
        counts: { blocking: 0, review: 1, outstanding_returns: 2 }, receivables: { source: 'ageing report' }, payables: { source: 'ageing report' },
        sources: [],
      }),
      history: [], defaults: { setup: SETUP },
    }
    render(<WpAgentPanel jobKey="ACME-1" />)
    const result = screen.getByRole('region', { name: 'Reconciliation result' })
    expect(result).toHaveTextContent('Reconciled subject to corrections')
    const bridge = within(result).getByRole('table', { name: 'Bridge' })
    expect(within(bridge).getByRole('row', { name: /Expected GST control balance/ })).toHaveTextContent('2,575.00')
    expect(within(bridge).getByRole('row', { name: /Other supported differences/ })).toHaveTextContent('(150.00)')
    expect(result).toHaveTextContent('Exceptions (0 blocking, 1 to review)')
    expect(result).toHaveTextContent('Dr GST 1,900.00; Cr Income Tax 1,900.00')
    expect(result).toHaveTextContent('Cleared in the return for 31-05-26')
    await userEvent.click(within(result).getByRole('button', { name: /Download workpaper/ }))
    expect(mocks.download).toHaveBeenCalledWith('r1', 'GST reconciliation Acme Trading Ltd 2026-03-31.xlsx')
  })

  it('a missing GST column pauses that side with the two choices', async () => {
    mocks.state = {
      latest: run({ status: 'Incomplete evidence', bridge: BRIDGE, exceptions: [], corrections: [], adjustments: [], counts: { blocking: 1, review: 0, outstanding_returns: 1 },
                    paused: { ap: { kind: 'no_gst_column', report: 'Accounts Payable', message: PAUSE } } }),
      history: [], defaults: { drive_link: 'https://drive.google.com/drive/folders/abc', setup: SETUP, choices: {} },
    }
    render(<WpAgentPanel jobKey="ACME-1" />)
    const paused = screen.getByRole('alert', { name: 'Accounts Payable paused' })
    expect(within(paused).getByRole('heading')).toHaveTextContent('Please re-upload the ageing report with the GST column')
    expect(paused).toHaveTextContent('The uploaded Accounts Payable ageing report does not include the GST attributable to outstanding balances.')
    await userEvent.click(within(paused).getByRole('button', { name: 'Upload revised report' }))
    expect(screen.getByLabelText(/AP ageing report link/)).toHaveFocus()
    await userEvent.click(within(paused).getByRole('button', { name: /continue with GL analysis/ }))
    expect(mocks.run).toHaveBeenCalledWith(expect.objectContaining({ choices: { ap_gl_fallback: true } }))
  })

  it('shows progress while it runs', () => {
    mocks.state = {
      latest: { ...run({}, 'running'), progress: [{ stage: 'read', state: 'done', label: '9 documents found', counts: null },
                                                 { stage: 'compared', state: 'running', label: 'Reconciling', counts: null }] },
      history: [], defaults: { setup: SETUP },
    }
    render(<WpAgentPanel jobKey="ACME-1" />)
    expect(screen.getByRole('region', { name: 'Progress' })).toHaveTextContent('9 documents found')
    expect(screen.getByRole('button', { name: 'Reconciling…' })).toBeDisabled()
  })

  it('a radio button chooses the wages or ICA agent, with its own settings, and runs it (10 Nov 2026)', async () => {
    render(<WpAgentPanel jobKey="ACME-1" />)
    const picker = screen.getByRole('group', { name: 'Reconciliation agent' })
    expect(within(picker).getByRole('radio', { name: 'GST reconciliation' })).toBeChecked()
    await userEvent.click(within(picker).getByRole('radio', { name: 'Imputation (ICA) reconciliation' }))
    expect(mocks.agents.at(-1)).toBe('ica')
    const form = screen.getByRole('form', { name: 'WP Agent inputs' })
    expect(within(form).queryByLabelText('GST basis')).toBeNull()
    expect(within(form).queryByLabelText(/AR ageing report link/)).toBeNull()
    await userEvent.type(within(form).getByLabelText(/Google Drive link/), 'https://drive.google.com/drive/folders/ICA')
    await userEvent.type(within(form).getByLabelText('Opening ICA balance (NZD)'), '1146.26')
    await userEvent.click(within(form).getByRole('button', { name: 'Run reconciliation' }))
    expect(mocks.run).toHaveBeenCalledWith(expect.objectContaining({ agent: 'ica', setup: expect.objectContaining({ opening_ica: '1146.26' }) }))
    await userEvent.click(within(picker).getByRole('radio', { name: 'Wages (PAYE) reconciliation' }))
    expect(mocks.agents.at(-1)).toBe('wages')
    expect(screen.getByLabelText('Opening IRD payroll payable (NZD)')).toBeInTheDocument()
  })

  it('shows the wages conclusions and statement and names the workpaper after the agent', async () => {
    mocks.state = {
      latest: {
        ...run({
          status: 'Reconciled subject to corrections', summary: 'Both reconciled subject to one correction.', paused: {}, exceptions: [], sources: [],
          conclusions: [{ label: 'Payroll expense', status: 'Reconciled subject to corrections', residual: '0.00' },
                        { label: 'Payroll liabilities', status: 'Reconciled subject to corrections', residual: '0.00' }],
          lines: [{ label: 'Payroll expense', heading: true }, { label: 'IRD-based employer-cost baseline', value: '178599.68', strong: true },
                  { label: 'IRD payroll principal payable at the balance date', value: '3566.82', strong: true }],
          corrections: [{ id: 'P1', title: 'IRD payment debited to salary expense', expense_effect: '-3766.84', liability_effect: '-3766.84', explanation: '',
                          evidence: [], status: 'proposed', lines: [{ account: 'PAYE Payable', debit: '3766.84', credit: '0.00' }] }],
        }),
        kind: 'wages',
      },
      history: [], defaults: { setup: SETUP },
    }
    render(<WpAgentPanel jobKey="ACME-1" />)
    const result = screen.getByRole('region', { name: 'Reconciliation result' })
    expect(within(result).queryByRole('table', { name: 'Bridge' })).toBeNull()
    expect(within(result).getByRole('table', { name: 'Conclusions' })).toHaveTextContent('Payroll liabilities')
    expect(within(within(result).getByRole('table', { name: 'Statement' }))
      .getByRole('row', { name: /employer-cost baseline/ })).toHaveTextContent('178,599.68')
    expect(result).toHaveTextContent('expense effect (3,766.84); liability effect (3,766.84)')
    await userEvent.click(within(result).getByRole('button', { name: /Download workpaper/ }))
    expect(mocks.download).toHaveBeenCalledWith('r1', 'Wages (PAYE) reconciliation Acme Trading Ltd 2026-03-31.xlsx')
  })

  it('the electronic workpapers agent takes the workpapers chosen by toggle buttons (16 Nov 2026)', async () => {
    render(<WpAgentPanel jobKey="ACME-1" />)
    await userEvent.click(screen.getByRole('radio', { name: 'Electronic workpapers (CCH)' }))
    expect(mocks.agents.at(-1)).toBe('ewp')
    const form = screen.getByRole('form', { name: 'WP Agent inputs' })
    const choices = within(form).getByRole('group', { name: 'Workpapers to prepare' })
    expect(within(choices).queryByRole('button', { name: /L1/ })).toBeNull()  // GST is its own agent
    await userEvent.click(within(choices).getByRole('button', { name: /V2 Use of home/ }))
    expect(within(choices).getByRole('button', { name: /V2 Use of home/ })).toHaveAttribute('aria-pressed', 'false')
    await userEvent.type(within(form).getByLabelText(/Google Drive link/), 'https://drive.google.com/drive/folders/TMC')
    await userEvent.click(within(form).getByRole('button', { name: 'Prepare workpapers' }))
    const sent = mocks.run.mock.calls.at(-1)![0]
    expect(sent.agent).toBe('ewp')
    expect(sent.workpapers).not.toContain('V2')
    expect(sent.workpapers).toContain('F1.1')
  })

  it('the electronic workpapers are shown by workpaper, corrected cell by cell, saved, then downloaded', async () => {
    mocks.save.mockClear()
    const fields = [
      { id: 'a', wp: 'F1.1', sheet: 'F1.1', cell: 'I12', label: 'Closing balance per bank statement', value: '101868.92', agent_value: '101868.92',
        kind: 'money', source: 'S3 Banking reconciliation report', how: 'document', status: 'review', note: '', editable: true },
      { id: 'b', wp: 'T2', sheet: 'T2', cell: 'G17', label: 'Interest 1 - gross', value: '21741.18', agent_value: '21741.18', kind: 'money',
        source: 'S5 IRD income summary', how: 'document', status: 'verified', note: '', editable: true },
    ]
    mocks.state = {
      latest: {
        ...run({
          status: 'Prepared - review', summary: 'Prepared for review.', exceptions: [{ id: 'x', wp: 'F1.1', code: 'no_statement', severity: 'review',
            text: "The closing balance is the software's expected statement balance.", next_evidence: 'The bank statement.', refs: [], amount: null }],
          fields, edits: [], journals: [],
          workpapers: [{ key: 'F1.1', title: 'Bank reconciliation', purpose: 'Bank', status: 'Prepared - review', fields: 1,
            checks: [{ wp: 'F1.1', label: 'Bank vs ledger', workpaper: '101868.92', ledger: '101868.92', variance: '0.00', status: 'agrees', note: '' }],
            exceptions: ['x'] },
          { key: 'T2', title: 'Investment income', purpose: 'Interest', status: 'Prepared', fields: 1, checks: [], exceptions: [] }],
          inventory: [{ sid: 'S9', name: 'V5 - Accountancy Fee Statement.pdf', path: '', kind: 'fee_statement', wp: 'V5', entity: 'other',
            status: 'excluded', note: "doesn't name the entity" }],
        }),
        kind: 'ewp',
      },
      history: [], defaults: { setup: SETUP },
    }
    render(<WpAgentPanel jobKey="ACME-1" />)
    const result = screen.getByRole('region', { name: 'Electronic workpapers' })
    expect(within(result).getByRole('table', { name: 'Checks' })).toHaveTextContent('agrees')
    expect(result).toHaveTextContent("software's expected statement balance")
    const cell = within(result).getByLabelText('Closing balance per bank statement (F1.1!I12)')
    await userEvent.clear(cell)
    await userEvent.type(cell, '101900')
    expect(within(result).getByRole('button', { name: /Download workbook/ })).toBeDisabled()  // save first
    await userEvent.click(within(result).getByRole('button', { name: 'Save 1 change' }))
    expect(mocks.save).toHaveBeenCalledWith([{ id: 'a', value: '101900' }], expect.anything())
    await userEvent.click(within(within(result).getByRole('group', { name: 'Workpapers' })).getByRole('button', { name: 'Documents' }))
    expect(within(result).getByRole('table', { name: 'Documents' })).toHaveTextContent('excluded')
  })
})
