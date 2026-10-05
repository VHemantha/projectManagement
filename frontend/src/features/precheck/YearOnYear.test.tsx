import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { YearOnYear } from './YearOnYear'
import type { YearOnYear as Analysis } from '@/api/precheck'

const analysis: Analysis = {
  available: true,
  how: 'model',
  this_year: 'FY2026',
  last_year: 'FY2025',
  period: '01 Apr 2025 to 31 Mar 2026',
  baseline: ['1. Medical Locum 2025 - Final TB.xlsx'],
  documents: { this_year: 8, last_year: 49 },
  summary: ['Bank opens at 18,479.45, matching last year, but stops on 27 Feb 2026.'],
  checks: [
    { label: "This year's opening bank balance equals last year's closing balance", passed: true, detail: 'opening 18,479.45, closing 18,479.45.', evidence_ids: ['E1', 'E2'] },
    { label: 'Bank data covers the whole year', passed: false, detail: 'ends 27 Feb 2026, before 31 Mar 2026.', evidence_ids: ['E1'] },
  ],
  bank: [{ account: '01-0702-0311954-00', from: '02 Apr 2025', to: '27 Feb 2026', opening: 18479.45, closing: 8813.51, money_in: 73338.94, money_out: 83004.88, transactions: 34 }],
  lines: [
    { id: 'P1', label: 'Contract Work', section: 'Income', last_year: 18330, year_before: 61250, this_year: null, change: null, change_pct: null, status: 'partly',
      comment: 'Receipts from People 2.0 look like contract income.', question: 'Obtain March 2026 bank data.',
      refs: [{ id: 'B1.1', label: 'People 2.0 New Z: 10 payments, total 73,338.94', evidence_id: 'E3' }], evidence_ids: ['E4', 'E3'] },
    { id: 'P8', label: 'Insurance', section: 'Expenses', last_year: 1255, year_before: 1255, this_year: null, change: null, change_pct: null, status: 'not_yet',
      comment: 'No insurance payment seen this year.', question: 'Ask for the insurance invoice.', refs: [], evidence_ids: ['E5'] },
    { id: 'P3', label: 'Depreciation - Motor Vehicles', section: 'Expenses', last_year: 4992.11, year_before: 7131.59, this_year: null, change: null, change_pct: null,
      status: 'at_year_end', comment: 'Worked out when the accounts are prepared.', question: '', refs: [], evidence_ids: [] },
  ],
  new_this_year: [{ text: 'Two tax certificates were received.', refs: [{ id: 'D7', label: 'Tax_Certificate_2026-03-31.pdf', evidence_id: 'E6' }] }],
  evidence: {
    E1: { file_name: '01-0702…xlsx', location: "sheet 'Transactions', row 35", quote: 'row 35: …', drive_url: 'https://drive.example/bank' },
    E2: { file_name: 'Bank Balance.pdf', location: 'page 1', quote: 'Closing balance 18,479.45', drive_url: 'https://drive.example/py-bank' },
    E3: { file_name: '01-0702…xlsx', location: "sheet 'Transactions', row 3", quote: 'People 2.0', drive_url: 'https://drive.example/bank' },
    E4: { file_name: 'Final TB.xlsx', location: "sheet 'Trial Balance', row 6", quote: 'Contract Work 18330', drive_url: 'https://drive.example/tb' },
    E5: { file_name: 'Final TB.xlsx', location: "sheet 'Trial Balance', row 9", quote: 'Insurance 1255', drive_url: 'https://drive.example/tb' },
    E6: { file_name: 'Tax_Certificate_2026-03-31.pdf', location: 'file in the task folder', quote: 'Tax_Certificate', drive_url: 'https://drive.example/cert' },
  },
}

describe('YearOnYear', () => {
  it('shows the comparison, the checks and the bank received this year', () => {
    render(<YearOnYear analysis={analysis} />)
    expect(screen.getByRole('heading', { name: /Compared with last year/ })).toHaveTextContent('FY2025 → FY2026')
    expect(screen.getByText(/Baseline: 1\. Medical Locum 2025 - Final TB\.xlsx/)).toHaveTextContent('8 documents received this year')
    expect(screen.getByText('AI summary')).toBeInTheDocument()
    const checks = screen.getByRole('list', { name: 'Checks against last year' })
    expect(within(checks).getByLabelText('Passed')).toBeInTheDocument()
    expect(within(checks).getByLabelText('Failed')).toBeInTheDocument()
    expect(within(checks).getByRole('link', { name: /last year/ })).toHaveAttribute('href', 'https://drive.example/py-bank')
    const bank = screen.getByRole('table', { name: 'Bank received this year' })
    expect(bank).toHaveTextContent('18,479.45')
    expect(bank).toHaveTextContent('73,338.94')
  })

  it('lists what needs attention first, and every line opens its source', async () => {
    render(<YearOnYear analysis={analysis} />)
    expect(screen.getByText(/2 of 3 need attention/)).toBeInTheDocument()
    expect(screen.getByText('Not received yet')).toBeInTheDocument()
    expect(screen.queryByText('Depreciation - Motor Vehicles')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^Insurance/ })).toHaveAttribute('href', 'https://drive.example/tb')
    expect(screen.getByRole('link', { name: /People 2\.0 New Z: 10 payments/ })).toHaveAttribute('href', 'https://drive.example/bank')
    expect(screen.getByText('Ask for the insurance invoice.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Show all lines' }))
    expect(screen.getByText('Depreciation - Motor Vehicles')).toBeInTheDocument()
    expect(screen.getByText('At year end')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show only what needs attention' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('link', { name: /Tax_Certificate_2026-03-31\.pdf/ })).toHaveAttribute('href', 'https://drive.example/cert')
  })
})
