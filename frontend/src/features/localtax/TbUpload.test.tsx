import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TbUpload } from './TbUpload'

const m = vi.hoisted(() => {
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), reset: vi.fn(), isPending: false, isError: false, isSuccess: false, error: null as unknown, data: undefined as unknown })
  return { idle, tb: idle(), attach: idle(), extract: idle(), decide: idle() }
})

vi.mock('@/api/issues', async (orig) => ({ ...(await orig<typeof import('@/api/issues')>()), useUploadAttachment: () => m.attach }))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useUploadTb: () => m.tb, useExtract: () => m.extract, useDecideExtraction: () => m.decide,
}))

describe('Uploading the trial balance of a Local client (AFIT)', () => {
  beforeEach(() => {
    for (const k of ['tb', 'attach', 'extract', 'decide'] as const) m[k] = m.idle()
  })

  it('reads an Excel or CSV trial balance by code', async () => {
    render(<TbUpload taskKey="LOC-1" />)
    const panel = screen.getByRole('region', { name: 'Upload the trial balance' })
    expect(within(panel).getByText('Not uploaded yet')).toBeInTheDocument()
    const file = new File(['Code,Account,Debit,Credit\n4000,Sales,,100\n1000,Bank,100,\n'], 'tb.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByLabelText('Trial balance file'), file)
    expect(m.tb.mutate).toHaveBeenCalledWith(file, expect.anything())
    expect(m.attach.mutateAsync).not.toHaveBeenCalled()
  })

  it('offers Local_Tax_AI for a PDF trial balance, and uses it only once confirmed', async () => {
    m.attach.mutateAsync = vi.fn().mockResolvedValue({ id: 9 })
    m.extract.mutate = vi.fn((_vars, opts) => opts.onSuccess({ extraction: { id: 5, kind: 'trial_balance', document: 'tb.pdf', status: 'pending', created_at: '',
      data: { lines: [{ code: '4000', description: 'Sales', amount: '-100', category: '', comparative: '', cite: 'p1' }], gaps: [], summary: '' } } }))
    render(<TbUpload taskKey="LOC-1" accounts={12} />)
    expect(screen.getByRole('button', { name: /Replace TB/ })).toBeInTheDocument()
    await userEvent.upload(screen.getByLabelText('Trial balance file'), new File(['%PDF'], 'tb.pdf', { type: 'application/pdf' }))
    expect(m.tb.mutate).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /Read tb.pdf with Local_Tax_AI/ }))
    expect(m.extract.mutate).toHaveBeenCalledWith({ attachmentId: 9, kind: 'trial_balance' }, expect.anything())
    const read = screen.getByLabelText('Trial balance read by AI')
    expect(read).toHaveTextContent('Sales')
    await userEvent.click(within(read).getByRole('button', { name: /Confirm and use/ }))
    expect(m.decide.mutate).toHaveBeenCalledWith({ id: 5, decision: 'confirm', use_as: 'trial_balance' }, expect.anything())
  })
})
