import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FinancialStatementsStage } from './FinancialStatementsStage'
import { RulesReviewPage } from './RulesReviewPage'
import { FixedAssetRegister } from './Schedules'
import { StageControls } from './Shared'
import type { LocalTaxState, RuleRegister } from '@/api/localTax'

const m = vi.hoisted(() => {
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), reset: vi.fn(), isPending: false, isError: false, error: null as unknown, data: undefined })
  return { idle, stage: idle(), review: idle(), field: idle(), check: idle(), register: null as unknown }
})

vi.mock('@/api/issues', async (orig) => ({ ...(await orig<typeof import('@/api/issues')>()), useUploadAttachment: m.idle }))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useMessages: () => ({ data: { messages: [], extractions: [] }, isLoading: false }),
  useAskLocalTax: m.idle, useSaveLocalTax: m.idle, usePutTb: m.idle, useMapLine: m.idle, useAiAgent: m.idle, useProposeAdjustment: m.idle,
  useEditAdjustment: m.idle, useDecideAdjustment: m.idle, useUploadTb: m.idle, useExtract: m.idle, useDecideExtraction: m.idle,
  useSetStage: () => m.stage, useReviewRule: () => m.review, useReviewField: () => m.field, useRuleCheck: () => m.check,
  useRuleRegister: () => ({ data: m.register, isLoading: false, isError: false, error: null }),
}))

const state = {
  engagement: {
    id: 1, task: 'LOC-1', entity_type: 'company', residency: 'resident', year_of_assessment: '2024/25', fy_end: '2025-03-31', tax_type: 'CIT',
    legal_name: 'ABC', client_name: 'ABC', tin: '1', nic_or_reg: 'PV1', address: '', activity: 'Trade', reporting_framework: 'smes', audited: true,
    expected_tax: null, expected_basis: 'total', data: {}, stages: { questionnaire: { status: 'approved' }, fs: { status: 'approved' },
      computation: { status: 'in_progress' }, return: { status: 'not_started' } }, version: 1, can_approve: true, updated_at: '',
  },
  financials: { kind: 'company', tb: [], unmapped: [], checks: [] },
  computation: null, reverse: null, return: null, alerts: [], years: ['2024/25'], adjustments: [],
  statements: {
    equity: { rows: [{ label: 'Balance at the start of the year', share_capital: '10000', reserves: '0', retained_earnings: '5000', total: '15000', kind: 'subtotal' },
      { label: 'Balance at the end of the year', share_capital: '12000', reserves: '0', retained_earnings: '17500', total: '29500', kind: 'total' }],
      check: { label: 'Closing equity agrees', passed: true, difference: '0' }, notes: [] },
    cash_flows: { available: true, net_change: '14500', opening_cash: '6000', closing_cash: '20500', notes: [],
      check: { label: 'Opening cash + net change = closing cash', passed: true, difference: '0' },
      sections: [{ key: 'operating', title: 'Cash flows from operating activities', rows: [{ label: 'Profit before tax', amount: '17500', note: '' }],
        subtotal: { label: 'Cash generated from operations', amount: '19000' }, after: [], total: { label: 'Net cash from operating activities', amount: '15500' } }] },
    notes: [{ no: 2, key: 'policies', title: 'Policies', policies: [{ key: 'ppe', title: 'Property, plant and equipment', text: 'Cost less depreciation.', standard: true }] },
      { no: 3, key: 'revenue', title: 'Revenue', total: '50000', total_comparative: '40000', lines: [{ code: '4000', name: 'Sales', amount: '50000', comparative: '40000' }] },
      { no: 4, key: 'events', title: 'Events after the reporting period', text: '[To be completed by the accountant.]', to_complete: true, editable: true }],
    audit_report: { label: 'DRAFT TEMPLATE - NOT AN AUDIT OPINION', title: "Independent Auditor's Report", addressee: 'To the shareholders of ABC',
      sections: [{ title: 'Opinion', text: '[To be completed by the auditor.]' }], signature: '[Auditor]' },
  },
} as unknown as LocalTaxState

describe('The Local Tax workflow, Phases 2-4 (AFIT)', () => {
  beforeEach(() => {
    for (const k of ['stage', 'review', 'field', 'check'] as const) m[k] = m.idle()
  })

  it('shows the full statements: changes in equity, cash flows, notes, policies and the draft audit report', async () => {
    render(<MemoryRouter><FinancialStatementsStage taskKey="LOC-1" state={state} onNext={() => {}} /></MemoryRouter>)
    const nav = screen.getByRole('list', { name: 'Financial statement sections' })
    await userEvent.click(within(nav).getByRole('button', { name: /Changes in Equity/ }))
    expect(within(screen.getByRole('table', { name: 'Statement of changes in equity' })).getByText('29,500')).toBeInTheDocument()
    await userEvent.click(within(nav).getByRole('button', { name: /Cash Flows/ }))
    expect(within(screen.getByRole('table', { name: 'Statement of cash flows' })).getByText('Net cash from operating activities')).toBeInTheDocument()
    await userEvent.click(within(nav).getByRole('button', { name: /Notes to the FS/ }))
    expect(screen.getByRole('region', { name: 'Note 3' })).toHaveTextContent('Sales')
    await userEvent.click(within(screen.getByRole('region', { name: 'Note 4' })).getByRole('button', { name: /Write/ }))
    expect(screen.getByRole('textbox', { name: 'Events after the reporting period text' })).toBeInTheDocument()
    await userEvent.click(within(nav).getByRole('button', { name: /Accounting Policies/ }))
    expect(screen.getByText('Standard wording')).toBeInTheDocument()
    await userEvent.click(within(nav).getByRole('button', { name: /Audit Report/ }))
    expect(screen.getByRole('heading', { name: /DRAFT TEMPLATE - NOT AN AUDIT OPINION/ })).toBeInTheDocument()
  })

  it('saves the fixed asset register the capital allowance schedule is worked out from', async () => {
    const onSave = vi.fn()
    render(<FixedAssetRegister rows={[]} onSave={onSave} busy={false} />)
    await userEvent.click(screen.getByRole('button', { name: /Add asset/ }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Asset' }), 'Lathe')
    await userEvent.type(screen.getByRole('textbox', { name: 'Cost' }), '10000')
    await userEvent.click(screen.getByRole('button', { name: 'Save and recalculate' }))
    expect(onSave).toHaveBeenCalledWith([expect.objectContaining({ description: 'Lathe', asset_class: 'plant_machinery', cost: '10000' })])
  })

  it('asks before approving figures that rest on unvalidated rules', async () => {
    m.stage = { ...m.idle(), isError: true, error: { response: { status: 409, data: { needs_acknowledgement: true, unvalidated: ['company.standard_rate'] } } } }
    render(<StageControls taskKey="LOC-1" state={state} stage="computation" />)
    const dialog = screen.getByRole('alertdialog', { name: 'Approve with unvalidated rules' })
    expect(dialog).toHaveTextContent('company.standard_rate')
    await userEvent.click(within(dialog).getByRole('button', { name: /I accept/ }))
    expect(m.stage.mutate).toHaveBeenCalledWith({ stage: 'computation', status: 'approved', acknowledge: true })
  })

  it('lets a validator validate or correct a rule with the law relied on', async () => {
    m.register = {
      year_of_assessment: '2024/25', status: 'DRAFT', legislation: 'Inland Revenue Act No. 24 of 2017', validated: 0, total: 1, fields: [], can_validate: true,
      rules: [{ rule: 'company.standard_rate', label: '', value: 0.3, file_value: 0.3, ref: 'IRA First Schedule', validated: false, reviewed_by: '', reviewed_at: '',
        conditions: [], history: [] }],
    } satisfies RuleRegister
    render(<MemoryRouter initialEntries={['/local-tax/rules/2024-25']}><Routes><Route path="/local-tax/rules/:ya" element={<RulesReviewPage />} /></Routes></MemoryRouter>)
    const row = screen.getByRole('region', { name: 'company.standard_rate' })
    expect(row).toHaveTextContent('30%')
    expect(within(row).getByText('Requires validation')).toBeInTheDocument()
    await userEvent.click(within(row).getByRole('button', { name: /Correct/ }))
    const value = within(row).getByRole('textbox', { name: /Correct value/ })
    await userEvent.clear(value)
    await userEvent.type(value, '0.28')
    await userEvent.type(within(row).getByRole('textbox', { name: /Note/ }), 'Amended')
    await userEvent.click(within(row).getByRole('button', { name: 'Save the correction' }))
    expect(m.review.mutate).toHaveBeenCalledWith(expect.objectContaining({ rule: 'company.standard_rate', action: 'correct', value: '0.28', note: 'Amended' }),
      expect.anything())
  })
})
