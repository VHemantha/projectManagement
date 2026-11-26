import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { JournalRegister } from './Journals'
import { PpeSection } from './Ppe'
import { PriorYearComparatives, TbDraftPreview, TbInstructions } from './TbSources'
import type { LocalTaxState } from '@/api/localTax'

const m = vi.hoisted(() => {
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), reset: vi.fn(), isPending: false, isError: false, error: null as unknown, data: undefined })
  return { idle, propose: idle(), decide: idle(), reverse: idle(), approve: idle(), story: idle(), useStory: idle(), prior: idle(), apply: idle() }
})

vi.mock('@/api/issues', async (orig) => ({
  ...(await orig<typeof import('@/api/issues')>()),
  useUploadAttachment: m.idle,
  useAttachments: () => ({ data: [{ id: 7, filename: 'invoice.pdf' }] }),
}))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useProposeAdjustment: () => m.propose, useDecideAdjustment: () => m.decide, useReverseJournal: () => m.reverse,
  useApproveDepreciation: () => m.approve, useSavePolicy: m.idle, useSaveLocalTax: m.idle, usePpeClassify: m.idle, useExtract: m.idle,
  useDecideExtraction: m.idle, useTbStory: () => m.story, useUseStoryTb: () => m.useStory, usePriorFs: () => m.prior,
  useApplyComparatives: () => m.apply,
}))

const engagement = {
  id: 1, task: 'LOC-1', entity_type: 'company', residency: 'resident', year_of_assessment: '2025/26', fy_end: '2026-03-31', tax_type: 'CIT',
  legal_name: 'ABC', client_name: 'ABC', tin: '1', nic_or_reg: 'PV1', address: '', activity: 'Trade', reporting_framework: 'smes', audited: false,
  expected_tax: null, expected_basis: 'total', data: {}, stages: {}, version: 1, can_approve: true, updated_at: '',
}
const tb = [{ code: '6090', name: 'Audit fee', amount: '0', comparative: null, heading: 'admin_expenses' },
  { code: '2020', name: 'Accruals', amount: '0', comparative: null, heading: 'trade_payables' }]

const base = { engagement, financials: { kind: 'company', tb, unmapped: [], checks: [] }, computation: null, reverse: null, return: null, alerts: [],
  years: [], adjustments: [] }

describe('PPE & depreciation, journals, the dummy trial balance and comparatives (AFIT, 24 Nov 2026)', () => {
  beforeEach(() => {
    for (const k of ['propose', 'decide', 'reverse', 'approve', 'story', 'useStory', 'prior', 'apply'] as const) m[k] = m.idle()
  })

  it('enters a journal with debit and credit columns and proposes it only when it balances', async () => {
    const state = { ...base, journals: { journals: [], accounts: [], approved: 0, proposed: 0 } } as unknown as LocalTaxState
    render(<JournalRegister taskKey="LOC-1" state={state} />)
    const codes = screen.getAllByRole('combobox', { name: 'Account code' })
    await userEvent.type(codes[0], '6090')
    await userEvent.type(codes[1], '2020')
    await userEvent.type(screen.getAllByRole('textbox', { name: 'Debit' })[0], '60000')
    await userEvent.type(screen.getByRole('textbox', { name: /Narration/ }), 'Audit fee for the year')
    const propose = screen.getByRole('button', { name: 'Propose for approval' })
    expect(propose).toBeDisabled()
    expect(screen.getByText(/Out of balance by/)).toBeInTheDocument()
    await userEvent.type(screen.getAllByRole('textbox', { name: 'Credit' })[1], '60000')
    expect(propose).toBeEnabled()
    await userEvent.click(propose)
    expect(m.propose.mutate.mock.calls[0][0]).toMatchObject({
      kind: 'journal', reason: 'Audit fee for the year', entry_date: '2026-03-31',
      lines: [{ code: '6090', name: 'Audit fee', amount: '60000' }, { code: '2020', name: 'Accruals', amount: '-60000' }],
    })
  })

  it('lists the register and reverses an approved journal (the depreciation journal is managed by its schedule)', async () => {
    const journals = [
      { id: 1, ref: 'JE-001', entry_date: '2026-03-31', label: 'Accrue audit fee', kind: 'journal', scope: 'accounting', status: 'approved', reason: 'Audit fee',
        lines: [{ code: '6090', name: 'Audit fee', amount: '60000.00' }, { code: '2020', name: 'Accruals', amount: '-60000.00' }], history: [], created_by: 'Pat',
        decided_by: 'Lee', reversed_by: [], managed: false },
      { id: 2, ref: 'JE-DEP', entry_date: '2026-03-31', label: 'Depreciation for the year', kind: 'journal', scope: 'accounting', status: 'approved', reason: 'Schedule',
        lines: [{ code: '6040', name: 'Depreciation', amount: '1000.00' }, { code: '1511', name: 'Acc dep', amount: '-1000.00' }], history: [], created_by: 'Lee',
        decided_by: 'Lee', reversed_by: [], managed: true },
    ]
    const state = { ...base, journals: { journals, accounts: [{ code: '6090', name: 'Audit fee', heading: 'admin_expenses', original: '0', journals: '60000', adjusted: '60000' }],
      approved: 2, proposed: 0 } } as unknown as LocalTaxState
    render(<JournalRegister taskKey="LOC-1" state={state} />)
    const reg = screen.getByRole('table', { name: 'Journal register' })
    expect(within(reg).getByText('JE-001')).toBeInTheDocument()
    expect(within(reg).getByText('From the depreciation schedule')).toBeInTheDocument()
    expect(within(reg).queryByRole('button', { name: 'Reverse JE-DEP' })).toBeNull()
    await userEvent.click(within(reg).getByRole('button', { name: 'Reverse JE-001' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Why reverse' }), 'Billed after the year end')
    await userEvent.click(screen.getByRole('button', { name: 'Propose reversal' }))
    expect(m.reverse.mutate.mock.calls[0][0]).toEqual({ id: 1, reason: 'Billed after the year end' })
  })

  it('shows the depreciation schedule and posts the journal on approval', async () => {
    const cat = { key: 'computer_equipment', label: 'Computer equipment', method: 'straight_line', rate: '0.25', residual: '0',
      cost: { opening: '1000000', additions: '250000', disposals: '0', closing: '1250000' },
      accumulated: { opening: '300000', charge: '302083.26', disposals: '0', closing: '602083.26' }, nbv: { opening: '700000', closing: '647916.74' },
      monthly: Array(12).fill('25173.61'), fully_depreciated: false, opening_source: 'Trial balance', additions: [], disposals: [] }
    const ppe = {
      policy: [{ key: 'computer_equipment', label: 'Computer equipment', method: 'straight_line', rate: '0.25', residual: '0' }],
      policy_about: { saved: true, client: 'ABC' }, methods: { straight_line: 'Straight-line', reducing_balance: 'Reducing balance' },
      accounts: [{ code: '1520', name: 'Computers', category: 'computer_equipment', role: 'cost', by: 'rule', amount: '1250000', comparative: '1000000' }],
      opening: { computer_equipment: { cost: '1000000', accumulated: '300000', source: 'Trial balance' } },
      schedule: { available: true, start: '2025-04-01', end: '2026-03-31', months: Array(12).fill('m'), categories: [cat], monthly: Array(12).fill('0'),
        totals: { cost_open: '1000000', additions: '250000', disposals_cost: '0', cost_close: '1250000', acc_open: '300000', charge: '302083.26', acc_disposals: '0',
          acc_close: '602083.26', proceeds: '0', gain: '0' }, flags: [], convention: 'A full month…' },
      journal: { lines: [{ code: '6040', name: 'Depreciation', amount: '302083.26', heading: 'admin_expenses' }, { code: '1521', name: 'Acc dep', amount: '-302083.26', heading: 'ppe' }],
        explain: [], residual: '0', charge: '302083.26' },
      status: 'not_approved', approved: {}, journal_ref: '', reconciliation: [], options: { proceeds_code: '' }, additions: [], disposals: [], blocking: [],
    }
    render(<PpeSection taskKey="LOC-1" state={{ ...base, ppe } as unknown as LocalTaxState} />)
    const sched = screen.getByRole('table', { name: 'Depreciation schedule' })
    expect(within(sched).getAllByText('302,083.26').length).toBeGreaterThan(0)
    expect(screen.getByRole('table', { name: 'Depreciation journal' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Approve and post the journal' }))
    expect(m.approve.mutate).toHaveBeenCalled()
  })

  it('drafts a trial balance from instructions, previewed before it is added; made-up figures are dummy data', async () => {
    const draft = (made_up: boolean) => ({
      rows: [{ code: '4000', name: 'Sales', heading: 'revenue', amount: '-30000000', comparative: '-26000000' },
        { code: '3100', name: 'Retained earnings', heading: 'retained_earnings', amount: '30000000', comparative: '26000000' }],
      story: 'A bakery with sales of 30 million', assumptions: made_up ? ['One shop.'] : [], notes: [], made_up })
    let got: unknown = null
    m.story.mutate = vi.fn((_text: string, opts?: { onSuccess?: (d: unknown) => void }) => opts?.onSuccess?.(draft(true)))
    const st = base as unknown as LocalTaxState
    const { rerender } = render(<TbInstructions taskKey="LOC-1" state={st} onDraft={(d) => (got = d)} />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Instructions for the trial balance' }), 'A bakery with sales of 30 million')
    await userEvent.click(screen.getByRole('button', { name: 'Generate draft' }))
    expect(got).toMatchObject({ made_up: true })
    rerender(<TbDraftPreview taskKey="LOC-1" state={st} preview={draft(true)} onDone={() => {}} />)
    expect(screen.getByText(/DUMMY DATA \(figures made up by Local_Tax_AI\)/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Replace the trial balance with this draft \(dummy data\)/ }))
    expect(m.useStory.mutate.mock.calls[0][0]).toMatchObject({ story: 'A bakery with sales of 30 million', made_up: true })
    // the accountant's own balances: not dummy data
    rerender(<TbDraftPreview taskKey="LOC-1" state={st} preview={draft(false)} onDone={() => {}} />)
    expect(screen.getByText(/drafted from your instructions/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Replace the trial balance with this draft' }))
    expect(m.useStory.mutate.mock.calls[1][0]).toMatchObject({ made_up: false })
  })

  it('reads last year\'s statements from a Drive link and applies the confirmed matches', async () => {
    m.prior.mutate = vi.fn((_b: unknown, opts?: { onSuccess?: (d: unknown) => void }) => opts?.onSuccess?.({ extraction: {
      id: 9, kind: 'prior_fs', document: 'fs.pdf', status: 'pending', created_at: '',
      data: { summary: 'FS 2025', gaps: [], lines: [{ description: 'Audit fees', amount: '50000', category: 'admin_expenses', code: '', comparative: '', cite: 'Note 3' }],
        proposals: [{ index: 0, action: 'match', code: '6090', heading: 'admin_expenses', why: 'A close name.' }] } } }))
    render(<PriorYearComparatives taskKey="LOC-1" state={base as unknown as LocalTaxState} />)
    await userEvent.type(screen.getByRole('textbox', { name: /Google Drive link/ }), 'https://drive.google.com/file/d/abc123def456ghi/view')
    await userEvent.click(screen.getByRole('button', { name: /Read from the link/ }))
    expect(m.prior.mutate.mock.calls[0][0]).toEqual({ link: 'https://drive.google.com/file/d/abc123def456ghi/view' })
    expect(screen.getByRole('combobox', { name: 'Account for Audit fees' })).toHaveValue('6090')
    await userEvent.click(screen.getByRole('button', { name: "Apply as this year's comparatives" }))
    expect(m.apply.mutate.mock.calls[0][0]).toMatchObject({ id: 9, mapping: [{ index: 0, action: 'match', code: '6090' }] })
  })
})
