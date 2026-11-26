import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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

vi.mock('@/api/issues', async (orig) => ({ ...(await orig<typeof import('@/api/issues')>()), useAttachments: () => ({ data: [{ id: 1 }, { id: 2 }] }), useUploadAttachment: idle }))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useLocalTax: () => ({ data: state, isLoading: false, isError: false, error: null }),
  useMessages: () => ({ data: { messages: [] }, isLoading: false }),
  useAskLocalTax: idle, useSaveLocalTax: idle, usePutTb: idle, useUploadTb: idle, useMapLine: idle, useProposeAdjustment: idle,
  useEditAdjustment: idle, useDecideAdjustment: idle, useSetStage: idle, useAiAgent: idle, useExtract: idle, useDecideExtraction: idle,
  useExtractions: () => ({ data: [], isLoading: false }),
  useDocuments: () => ({ isLoading: false, data: { documents: [{ id: 1, attachment_id: 1, name: 'bank.pdf', url: '', origin: 'drive', drive_path: '', drive_url: '',
    kind: 'bank_statement', summary: 'March statement', period_end: null, read_at: '2026-11-22', read_error: '', found: { fields: 1, lines: 0, balances: 1 } }],
    suggestions: [{ id: 7, target: 'field:tin', value: '114567890', sources: [{ document: 'bank.pdf', attachment_id: 1, document_id: 1, cite: 'p1' }], status: 'pending',
      edited: false, decided_by: '', decided_at: null }],
    flags: [{ id: 3, kind: 'inconsistent', target: 'field:tin', text: 'TIN differs between documents.', sources: [], status: 'open', resolution: '', resolved_by: '', resolved_at: null }],
    drive: { url: 'https://drive.google.com/drive/folders/abc', folder_id: 'abc', synced_at: null } } }),
  useDriveAccount: () => ({ data: { account_email: 'tasko@example.iam', configured: true } }),
  useLinkDrive: idle, useSyncDrive: idle, useDecideSuggestion: idle, useResolveFlag: idle, usePrefill: () => ({ ...idle(), progress: null }),
  downloadLocalTax: vi.fn(),
}))

function at(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/card" element={<LocalTaxOverview taskKey="LOC-1" />} />
        <Route path="/local-tax/:issueKey" element={<LocalTaxPage />} />
      </Routes>
    </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('The Local Tax workflow (Team 3 > Local cards, AFIT 22 Nov 2026)', () => {
  it('shows the card overview: four stages with status and progress, the tax summary and the reverse analysis', () => {
    at('/card')
    for (const t of ['1. Client Info', '2. Financial Statements', '3. Tax Computation', '4. Draft Tax Return']) {
      expect(screen.getByRole('article', { name: t })).toBeInTheDocument()
    }
    expect(within(screen.getByRole('article', { name: '2. Financial Statements' })).getByText('40%')).toBeInTheDocument()
    const summary = screen.getByRole('region', { name: 'Tax Summary' })
    expect(within(summary).getByText('Expected Tax Payment')).toBeInTheDocument()
    expect(within(summary).getByText('Required Taxable Income')).toBeInTheDocument()
    expect(within(summary).getByText(/11,666,666/)).toBeInTheDocument()
    expect(screen.getByText('ABC Trading (Pvt) Ltd')).toBeInTheDocument()
  })

  it('opens a stage in a full-screen window from its card; Back to AI Workflow returns to the overview', async () => {
    at('/card')
    await userEvent.click(within(screen.getByRole('article', { name: '4. Draft Tax Return' })).getByRole('button', { name: /Start/ }))
    const win = screen.getByRole('dialog')
    expect(within(win).getByRole('heading', { name: 'Draft Tax Return' })).toBeInTheDocument()
    const steps = within(win).getByRole('list', { name: 'Workflow stages' })
    for (const [step, heading] of [['Client Info', /Client Info/], ['Financial Statements', /Financial Statements/], ['Tax Computation', /Tax Computation/]] as const) {
      await userEvent.click(within(steps).getByRole('button', { name: new RegExp(step) }))
      expect(within(steps).getByRole('button', { name: new RegExp(step) })).toHaveAttribute('aria-current', 'step')
      expect(within(win).getAllByRole('heading', { name: heading }).length).toBeGreaterThan(0)
    }
    await userEvent.click(within(win).getByRole('button', { name: /Back: Financial Statements/ }))
    expect(within(steps).getByRole('button', { name: /Financial Statements/ })).toHaveAttribute('aria-current', 'step')
    await userEvent.click(within(win).getByRole('button', { name: /Back to AI Workflow/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('article', { name: '1. Client Info' })).toBeInTheDocument()
  })

  it('Client Info: Back and Next keep what was typed; the documents show each value with its source and the flags', async () => {
    at('/card')
    await userEvent.click(within(screen.getByRole('article', { name: '1. Client Info' })).getByRole('button', { name: /Continue/ }))
    const win = screen.getByRole('dialog')
    expect(within(win).getByRole('button', { name: /Back to AI Workflow/ })).toBeInTheDocument()
    expect(within(win).queryByRole('button', { name: /^← Back:|Back: / })).not.toBeInTheDocument() // step 1: no Back
    const tin = within(win).getAllByRole('textbox')[1]
    await userEvent.clear(tin)
    await userEvent.type(tin, '999')
    expect(within(win).getByRole('radio', { name: 'Full set of financial statements' })).toBeChecked()
    await userEvent.click(within(win).getByRole('button', { name: /Next: Supporting Documents/ }))
    const docs = within(win).getByRole('region', { name: 'Values to verify' })
    expect(docs).toHaveTextContent('bank.pdf — p1')
    expect(within(win).getByRole('region', { name: 'Issues to resolve' })).toHaveTextContent('TIN differs between documents.')
    expect(within(win).getByRole('region', { name: "Client's Google Drive folder" })).toHaveTextContent('tasko@example.iam')
    await userEvent.click(within(win).getByRole('button', { name: /^Back$/ }))  // the Supporting docs footer (the AFIT design)
    expect(within(win).getAllByRole('textbox')[1]).toHaveValue('999')
  })
})
