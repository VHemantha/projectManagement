import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FinancialStatementsStage } from './FinancialStatementsStage'
import { FsEditsBanner } from './FsFigures'
import { JournalRegister } from './Journals'
import { QuestionnaireStage } from './QuestionnaireStage'
import { ReportView } from './Report'
import { UpdateButton } from './Update'
import type { LocalTaxState } from '@/api/localTax'

const m = vi.hoisted(() => {
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(async () => ({})), reset: vi.fn(), isPending: false, isError: false, error: null as unknown,
    data: undefined as unknown })
  return { idle, save: idle(), edit: idle(), undo: idle(), post: idle(), update: idle(), propose: idle() }
})
vi.mock('@/api/issues', async (orig) => ({ ...(await orig<typeof import('@/api/issues')>()), useUploadAttachment: m.idle, useAttachments: () => ({ data: [] }) }))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useMessages: () => ({ data: { messages: [], extractions: [] }, isLoading: false }),
  useAskLocalTax: m.idle, useSaveLocalTax: () => m.save, usePutTb: m.idle, useMapLine: m.idle, useAiAgent: m.idle, useSetStage: m.idle,
  useFsEdit: () => m.edit, useUndoFsEdit: () => m.undo, usePostFsEdits: () => m.post, useUpdateWorkflow: () => m.update,
  useProposeAdjustment: () => m.propose, useDecideAdjustment: m.idle, useReverseJournal: m.idle, useExtract: m.idle, useDecideExtraction: m.idle,
  useUploadTb: m.idle, useTbStory: m.idle, useUseStoryTb: m.idle, usePriorFs: m.idle, useApplyComparatives: m.idle,
  useDocuments: () => ({ isLoading: false, data: { documents: [], suggestions: [], flags: [], drive: null } }),
  useDriveAccount: () => ({ data: { account_email: '', configured: false } }), useLinkDrive: m.idle, useSyncDrive: m.idle,
  useDecideSuggestion: m.idle, useResolveFlag: m.idle, usePrefill: () => ({ ...m.idle(), progress: null }),
}))

const pl = { revenue: '1450000', cost_of_sales: '0', gross_profit: '1450000', other_income: '0', admin_expenses: '2050000', distribution_expenses: '0',
  finance_costs: '0', pbt: '-600000', income_tax_expense: '0', profit: '-600000', oci: '0', total_comprehensive_income: '-600000' }
const engagement = {
  id: 1, task: 'LOC-1', entity_type: 'company', residency: 'resident', year_of_assessment: '2024/25', fy_end: '2025-03-31', tax_type: 'CIT',
  legal_name: 'ABC', client_name: 'ABC', tin: '1', nic_or_reg: 'PV1', address: '', activity: 'Trade', reporting_framework: 'smes', audited: false,
  expected_tax: null, expected_basis: 'total', data: {}, stages: { questionnaire: { status: 'approved' }, fs: { status: 'in_progress' },
    computation: { status: 'not_started' }, return: { status: 'not_started' } }, version: 1, can_approve: true, updated_at: '',
}
const unbalanced = { items: [{ heading: 'admin_expenses', label: 'Administrative expenses', delta: '50000.00', from: '2000000.00', to: '2050000.00', by: 'Pat', at: '' }],
  difference: '50000.00', balanced: false, needs_balance: true, journal: null, can_post: false }
const state = {
  engagement, computation: null, reverse: null, return: null, alerts: [], years: ['2024/25'], adjustments: [], levers: [],
  financials: { kind: 'company', pl: { current: pl, comparative: null }, unmapped: [], checks: [], has_comparative: false,
    bs: { cash: { label: 'Cash and cash equivalents', kind: 'asset', amount: '500000', comparative: null, lines: [] } }, totals: { assets: '500000', equity: '400000', liabilities: '50000' },
    tb: [{ code: '6100', name: 'Rent', amount: '1000000', comparative: null, heading: 'admin_expenses' },
      { code: 'EDIT:admin_expenses', name: 'Edited on the statements: Administrative expenses', amount: '50000', comparative: null, heading: 'admin_expenses', edit: true }] },
  statements: { scope: 'full', equity: null, cash_flows: null, notes: [], audit_report: null },
  fs_edits: unbalanced,
  report: { kind: 'compilation', label: 'Compilation report', date: '2025-06-30', date_text: '30 June 2025', draft_note: '', signature: ['AFIT CONNECT'],
    sections: [{ key: 'title', kind: 'title', text: 'COMPILATION REPORT TO THE SHAREHOLDERS OF ABC', standard: '', edited: false },
      { key: 'body', kind: 'para', text: 'On the basis of information provided by management we have compiled…', standard: '', edited: false }] },
} as unknown as LocalTaxState

describe('Team 3 > Local: report, editable statements, Update (AFIT, 26 Nov 2026)', () => {
  beforeEach(() => {
    for (const k of ['save', 'edit', 'undo', 'post', 'update', 'propose'] as const) m[k] = m.idle()
  })

  it('edits a line of the statements but never a total, and holds the stage while the edits are out of balance', async () => {
    render(<MemoryRouter><FinancialStatementsStage taskKey="LOC-1" state={state} onNext={() => {}} /></MemoryRouter>)
    const nav = screen.getByRole('list', { name: 'Financial statement sections' })
    expect(within(nav).getAllByRole('button')[0]).toHaveTextContent('Compilation Report')
    await userEvent.click(within(nav).getByRole('button', { name: /Profit or Loss/ }))
    const table = screen.getByRole('table', { name: 'Statement of profit or loss' })
    expect(within(table).queryByRole('button', { name: /Edit Gross Profit/ })).toBeNull()
    expect(within(table).queryByRole('button', { name: /Edit Profit for the Year/ })).toBeNull()
    const admin = within(table).getByRole('button', { name: /Edit Administrative Expenses/ })
    expect(admin).toHaveAttribute('data-edited', 'true')
    await userEvent.click(within(table).getByRole('button', { name: /Edit Revenue/ }))
    const input = within(table).getByRole('textbox', { name: 'New figure: Revenue' })
    await userEvent.clear(input)
    await userEvent.type(input, '1500000{Enter}')
    expect(m.edit.mutate.mock.calls[0][0]).toEqual({ heading: 'revenue', value: '1500000' })
    expect(screen.getAllByRole('alert').some((a) => /out of balance by 50,000/.test(a.textContent ?? ''))).toBe(true)
    expect(screen.getAllByRole('button', { name: /Next: Tax Computation/ }).every((b) => (b as HTMLButtonElement).disabled)).toBe(true)
    // the TB mapping sits at the top right, the edit shown there until posted
    await userEvent.click(screen.getByRole('button', { name: /^TB Mapping/ }))
    const tb = screen.getByRole('region', { name: 'TB Mapping' })
    expect(within(tb).getByText(/Edited on the statements: not in the TB/)).toBeInTheDocument()
  })

  it('offers to update the TB once the edits balance, and shows the journal waiting', async () => {
    const balanced = { ...unbalanced, items: [...unbalanced.items, { heading: 'trade_payables', label: 'Trade and other payables', delta: '-50000.00', from: '50000.00',
      to: '100000.00', by: 'Pat', at: '' }], difference: '0.00', balanced: true, can_post: true }
    const { rerender } = render(<FsEditsBanner taskKey="LOC-1" edits={balanced} />)
    await userEvent.click(screen.getByRole('button', { name: 'Update the TB' }))
    expect(m.post.mutate).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Undo the edit: Trade and other payables' }))
    expect(m.undo.mutate).toHaveBeenCalledWith('trade_payables')
    rerender(<FsEditsBanner taskKey="LOC-1" edits={{ ...balanced, can_post: false, journal: { id: 9, ref: 'JE-004', status: 'proposed' } }} />)
    expect(screen.getByRole('status', { name: 'Statement edits' })).toHaveTextContent('JE-004, waiting for approval')
    expect(screen.queryByRole('button', { name: 'Update the TB' })).toBeNull()
  })

  it("edits a paragraph of the report in the firm's format", async () => {
    render(<ReportView taskKey="LOC-1" state={state} />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit: body' }))
    const box = screen.getByRole('textbox', { name: 'Wording: body' })
    await userEvent.clear(box)
    await userEvent.type(box, 'Compiled from the books.')
    await userEvent.click(screen.getByRole('button', { name: /Save/ }))
    expect(m.save.mutate.mock.calls[0][0]).toEqual({ data: { report_text: { compilation: { body: 'Compiled from the books.' } } }, stage: 'fs' })
    expect(screen.getByRole('button', { name: 'Word' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'PDF' })).toBeInTheDocument()
  })

  it('updates the workflow and says what changed', async () => {
    m.update = { ...m.idle(), data: { changes: [{ key: 'profit', label: 'Profit for the year', from: '-550000.00', to: '-600000.00' }], first: false, at: '', state } }
    render(<UpdateButton taskKey="LOC-1" stage="fs" label="Update FS" />)
    await userEvent.click(screen.getByRole('button', { name: /Update FS/ }))
    expect(m.update.mutateAsync).toHaveBeenCalledWith('fs')
    expect(screen.getByRole('status')).toHaveTextContent('Profit for the year: (550,000) → (600,000)')
  })

  it('asks a company only for what its trial balance does not give, with the report type among the first questions', async () => {
    render(<MemoryRouter><QuestionnaireStage taskKey="LOC-1" state={state} onNext={() => {}} /></MemoryRouter>)
    const nav = screen.getByRole('list', { name: 'Client info sections' })
    const labels = within(nav).getAllByRole('button').map((b) => b.textContent?.trim())
    expect(labels).toEqual(['A. Client Details', 'B. Supporting Documents', 'C. Tax Credits & Payments', 'D. Expected Tax Payment', 'E. Disclosures for the Notes'])
    await userEvent.click(screen.getByRole('radio', { name: 'Audit report' }))
    expect(screen.getByRole('radio', { name: 'Audit report' })).toBeChecked()
    expect(screen.getByRole('button', { name: /Update/ })).toBeInTheDocument()
  })

  it('finds a journal account by its name', async () => {
    const st = { ...state, journals: { journals: [], accounts: [], approved: 0, proposed: 0 } } as unknown as LocalTaxState
    const { container } = render(<JournalRegister taskKey="LOC-1" state={st} />)
    const names = screen.getAllByRole('combobox', { name: 'Account name' })
    await userEvent.type(names[0], 'rent')
    expect(screen.getAllByRole('combobox', { name: 'Account code' })[0]).toHaveValue('6100')
    // the statement edits waiting to be posted are not accounts to journal to
    const options = [...container.querySelectorAll('datalist option')].map((o) => o.getAttribute('value'))
    expect(options).toContain('Rent')
    expect(options.some((v) => v?.startsWith('EDIT:') || v?.startsWith('Edited on'))).toBe(false)
  })
})
