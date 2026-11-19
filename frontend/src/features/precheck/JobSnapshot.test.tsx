import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { JobSnapshot } from './JobSnapshot'
import type { JobSnapshot as Snapshot, SourceRef } from '@/api/precheck'

const src = (id: string, label: string, evidence_id: string | null = null): SourceRef => ({ id, label, evidence_id })
const evidence = { e1: { file_name: 'Final TB 2025.xlsx', location: 'row 6', quote: 'Rental income 31,200', drive_url: 'https://drive.example/tb' } }

const snapshot: Snapshot = {
  written: true,
  changes: ['Revenue is now $31,200 (was $25,000 in the last pre-check).'],
  business_story: 'John and Kate Smith own one rental house at 12 Kauri Street, managed by Barfoot & Thompson.',
  story_flags: [],
  revenue_sources: [{ label: 'Rent', detail: '12 Kauri Street', sources: [] }],
  financial_story: 'Rent rose a little and interest fell, so the profit grew.',
  financial_flags: [],
  events: [
    { text: 'The ASB loan was refinanced in October 2025.', kind: 'financing', status: 'confirmed', sources: [src('Q5', 'Questionnaire: refinanced')], flags: [] },
    { text: 'The fixed asset account may include a new heat pump, but the invoice is not here yet.', kind: 'purchase', status: 'inferred', sources: [], flags: [] },
  ],
  ownership: {
    shareholders: [
      { name: 'John', percent: 50, sources: [] },
      { name: 'Kate', percent: 50, sources: [] },
    ],
    note: '',
    sources: [],
  },
  current_accounts: '',
  focus_areas: [{ area: 'Interest', why: 'The loan was refinanced, so the interest needs splitting at the date.', sources: [] }],
  understood: [{ text: 'Read the questionnaire and last year’s trial balance.', status: 'confirmed', sources: [] }],
  figures: {
    available: true,
    basis: 'trial_balance',
    year_label: 'Last year',
    comparative_label: 'Year before',
    kpis: [
      { label: 'Revenue', amount: 31200, comparative: 29900, change_pct: 4 },
      { label: 'Expenses', amount: 22630.18, comparative: 23002, change_pct: -2 },
      { label: 'Net profit', amount: 8569.82, comparative: 6898, change_pct: 24 },
    ],
    income: [{ label: 'Rental income', amount: 31200, comparative: 29900, source: src('T1', "Last year's trial balance: Rental income", 'e1') }],
    expenses: [{ label: 'Interest', amount: 14322.18, comparative: 15010, source: src('T4', "Last year's trial balance: Interest") }],
    asset_mix: [
      { label: 'Property', amount: 600000, comparative: 600000, lines: [{ label: '12 Kauri Street', amount: 600000, comparative: 600000, source: src('T7', 'TB: 12 Kauri Street') }] },
      { label: 'Cash and bank', amount: 4210, comparative: 3100, lines: [] },
    ],
    funding_mix: [
      { label: 'Bank borrowing', amount: 418000, comparative: 424000, lines: [] },
      { label: 'Equity (what is left for the owners)', amount: 186210, comparative: null, derived: true, lines: [] },
    ],
    current_accounts: [],
    this_year: null,
  },
}

describe('Job Snapshot (AFIT design requirements, 16 Nov 2026)', () => {
  it('tells the story first, with the figures code worked out and the change on the year before', () => {
    render(<JobSnapshot snapshot={snapshot} evidence={evidence} />)
    const s = screen.getByRole('region', { name: 'Job Snapshot' })
    expect(within(s).getByText(/own one rental house at 12 Kauri Street/)).toBeInTheDocument()
    expect(within(s).getByRole('list', { name: 'How it earns money' })).toHaveTextContent('Rent')
    expect(s).toHaveTextContent('Figures are worked out by code from last year\'s trial balance, with the year before beside them.')
    expect(s).toHaveTextContent('Revenue$31,200+4% vs year before')
    expect(within(s).getByRole('status')).toHaveTextContent('Revenue is now $31,200 (was $25,000 in the last pre-check).')
  })

  it('shows what it owns and how it is funded as composition bars, each group opening to its lines and sources', async () => {
    render(<JobSnapshot snapshot={snapshot} evidence={evidence} />)
    expect(screen.getByRole('img', { name: 'What it owns: Property $600,000, Cash and bank $4,210' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'How it is funded: Bank borrowing $418,000, Equity (what is left for the owners) $186,210' })).toBeInTheDocument()
    await userEvent.click(screen.getByText('Property'))
    expect(screen.getByText('12 Kauri Street', { selector: 'li' })).toBeInTheDocument()
    // A figure opens the document at its line.
    // A figure opens the document at its line, through its document icon (19 Nov 2026).
    const tb = screen.getByRole('link', { name: /^Trial balance: Final TB 2025\.xlsx, row 6/ })
    expect(tb).toHaveAttribute('href', 'https://drive.example/tb')
    expect(tb).toHaveTextContent('TB')
  })

  it('keeps ownership apart from current accounts, and marks each event confirmed or inferred', () => {
    render(<JobSnapshot snapshot={snapshot} evidence={evidence} />)
    expect(screen.getByRole('img', { name: 'Ownership: John 50%, Kate 50%' })).toBeInTheDocument()
    expect(screen.getByText(/Ownership shares and current-account balances are different things/)).toBeInTheDocument()
    const refinance = screen.getByText(/The ASB loan was refinanced/).closest('li')!
    expect(within(refinance).getByText('Confirmed')).toBeInTheDocument()
    expect(within(screen.getByText(/may include a new heat pump/).closest('li')!).getByText('Inferred')).toBeInTheDocument()
    expect(screen.getByText(/The loan was refinanced, so the interest needs splitting/)).toBeInTheDocument()
    expect(screen.getByText('What the AI understood')).toBeInTheDocument()
  })

  it('says so when there is nothing to work figures out from, and shows no percentages it was not given', () => {
    render(
      <JobSnapshot
        snapshot={{ ...snapshot, changes: [], figures: { available: false, basis: '', year_label: '', comparative_label: '' },
          ownership: { shareholders: [{ name: 'John', percent: null, sources: [] }], note: '', sources: [] } }}
        evidence={{}}
      />,
    )
    expect(screen.getByText(/No figures yet: last year's trial balance or financial statements were not found/)).toBeInTheDocument()
    expect(screen.getByText('Shareholders: John. Their shares are not shown in the documents read.')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /Ownership/ })).not.toBeInTheDocument()
  })
})
