import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LocalTaxOverview } from './LocalTaxOverview'
import { LocalTaxPage } from './LocalTaxPage'
import type { LocalTaxState } from '@/api/localTax'

const { idle, state } = vi.hoisted(() => {
const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isError: false, error: null, data: undefined })
const state: LocalTaxState = {
  engagement: {
    id: 1, task: 'LOC-1', entity_type: 'company', residency: 'resident', year_of_assessment: '2025/26', fy_end: '2026-03-31',
    tax_type: 'CIT', legal_name: 'ABC Trading (Pvt) Ltd', client_name: 'ABC', tin: '123456789', nic_or_reg: 'PV 1', address: 'Colombo',
    activity: 'Trading', reporting_framework: 'smes', audited: false, expected_tax: '3000000.00', expected_basis: 'total',
    data: { payments: [{ type: 'quarterly', amount: '500000', date: '2026-01-15', reference: 'Q3' }] },
    stages: {
      questionnaire: { status: 'approved' }, fs: { status: 'in_progress' },
      computation: { status: 'not_started' }, return: { status: 'not_started' },
    },
    version: 3, can_approve: true, updated_at: '2026-11-22T00:00:00Z',
  },
  financials: { kind: 'company', tb: [{ code: '4000', name: 'Sales', amount: '-50000000', comparative: null, heading: 'revenue' }], unmapped: [] },
  computation: {
    lines: [], taxable_income: '12000000.00', income_tax: '3600000.00', credits: '500000.00', payable: '3100000.00', pbt: '11500000.00',
    flags: [], rules: [], unvalidated: true,
  },
  reverse: {
    expected: '3000000.00', basis: 'total', calculated: '3100000.00', variance: '100000.00', taxable_income: '12000000.00',
    required_taxable_income: '11666666.67', taxable_income_difference: '333333.33', scenarios: [],
  },
  return: {
    sections: [{ key: 'basic', title: 'A. Basic information', fields: [{ code: 'B1', label: 'TIN', value: '123456789', source: 'Questionnaire', required: true, missing: false, kind: 'text' }] }],
    missing: [], note: 'Field codes are placeholders until validated.',
  },
  alerts: [], years: ['2024/25', '2025/26'], adjustments: [], levers: [],
  progress: { questionnaire: 100, fs: 40, computation: 0, return: 0 },
}
return { idle, state }
})

vi.mock('@/api/issues', async (orig) => ({ ...(await orig<typeof import('@/api/issues')>()), useAttachments: () => ({ data: [{ id: 1 }, { id: 2 }] }) }))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useLocalTax: () => ({ data: state, isLoading: false, isError: false, error: null }),
  useMessages: () => ({ data: { messages: [] }, isLoading: false }),
  useAskLocalTax: idle, useSaveLocalTax: idle, usePutTb: idle, useUploadTb: idle, useMapLine: idle, useProposeAdjustment: idle,
  useEditAdjustment: idle, useDecideAdjustment: idle, useSetStage: idle, useAiAgent: idle, useExtract: idle, useDecideExtraction: idle,
  useExtractions: () => ({ data: [], isLoading: false }),
  downloadLocalTax: vi.fn(),
}))

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/card" element={<LocalTaxOverview taskKey="LOC-1" />} />
        <Route path="/local-tax/:issueKey" element={<LocalTaxPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('The Local Tax workflow (Team 3 > Local cards, AFIT 22 Nov 2026)', () => {
  it('shows the card overview: four stages with status and progress, the tax summary and the reverse analysis', () => {
    at('/card')
    for (const t of ['1. Questionnaire', '2. Financial Statements', '3. Tax Computation', '4. Draft Tax Return']) {
      expect(screen.getByRole('article', { name: t })).toBeInTheDocument()
    }
    expect(within(screen.getByRole('article', { name: '2. Financial Statements' })).getByText('40%')).toBeInTheDocument()
    const summary = screen.getByRole('region', { name: 'Tax Summary' })
    expect(within(summary).getByText('Expected Tax Payment')).toBeInTheDocument()
    expect(within(summary).getByText('Required Taxable Income')).toBeInTheDocument()
    expect(within(summary).getByText(/11,666,666/)).toBeInTheDocument()
    expect(screen.getByText('ABC Trading (Pvt) Ltd')).toBeInTheDocument()
  })

  it('opens a stage full screen from its card, and the stepper moves between all four stages', async () => {
    at('/card')
    await userEvent.click(within(screen.getByRole('article', { name: '4. Draft Tax Return' })).getByRole('button', { name: /Start/ }))
    expect(screen.getByRole('heading', { name: 'Draft Tax Return' })).toBeInTheDocument()
    const steps = screen.getByRole('list', { name: 'Workflow stages' })
    for (const [step, heading] of [['Questionnaire', /Questionnaire/], ['Financial Statements', /Financial Statements/], ['Tax Computation', /Tax Computation/]] as const) {
      await userEvent.click(within(steps).getByRole('button', { name: new RegExp(step) }))
      expect(within(steps).getByRole('button', { name: new RegExp(step) })).toHaveAttribute('aria-current', 'step')
      expect(screen.getAllByRole('heading', { name: heading }).length).toBeGreaterThan(0)
    }
  })
})
