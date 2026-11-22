import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SupportingDocuments } from './SupportingDocuments'

const m = vi.hoisted(() => {
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), reset: vi.fn(), isPending: false, isError: false, isSuccess: false, error: null as unknown, data: undefined })
  return { idle, decide: idle(), resolve: idle(), prefill: { ...idle(), progress: null as unknown } }
})

vi.mock('@/api/issues', async (orig) => ({ ...(await orig<typeof import('@/api/issues')>()), useUploadAttachment: m.idle }))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useDocuments: () => ({ isLoading: false, data: {
    documents: [{ id: 1, attachment_id: 1, name: 'statement.pdf', url: '', origin: 'upload', drive_path: '', drive_url: '', kind: '', summary: '', period_end: null,
      read_at: null, read_error: '', found: { fields: 0, lines: 0, balances: 0 } }],
    suggestions: [{ id: 9, target: 'payments', value: { type: 'WHT', amount: '1165', reference: 'WHT on interest' },
      sources: [{ document: 'statement.pdf', attachment_id: 1, document_id: 1, cite: 'line 14' }], status: 'pending', edited: false, decided_by: '', decided_at: null }],
    flags: [{ id: 4, kind: 'missing', target: '', text: 'Page 3 is missing.', sources: [], status: 'open', resolution: '', resolved_by: '', resolved_at: null }],
    drive: { url: '', folder_id: '', synced_at: null } } }),
  useDriveAccount: () => ({ data: { account_email: 'tasko@example.iam', configured: true } }),
  useLinkDrive: m.idle, useSyncDrive: m.idle, useUploadTb: m.idle, useExtract: m.idle, useDecideExtraction: m.idle,
  usePrefill: () => m.prefill, useDecideSuggestion: () => m.decide, useResolveFlag: () => m.resolve,
}))

describe('Client Info > Supporting Documents (Team 3 > Local cards)', () => {
  it('reads new documents with AI, lets the accountant edit before confirming, and resolve flags with how', async () => {
    render(<QueryClientProvider client={new QueryClient()}><SupportingDocuments taskKey="LOC-1" isCompany tbCount={0} /></QueryClientProvider>)
    expect(screen.getByRole('region', { name: 'Upload the trial balance' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Read 1 new document with AI/ }))
    expect(m.prefill.mutate).toHaveBeenCalledWith({ names: { 1: 'statement.pdf' } })
    const review = screen.getByRole('region', { name: 'Values to verify' })
    expect(review).toHaveTextContent('statement.pdf — line 14')
    const value = within(review).getByRole('textbox')
    await userEvent.clear(value)
    await userEvent.type(value, '1200')
    await userEvent.click(within(review).getByRole('button', { name: /Confirm edited/ }))
    expect(m.decide.mutate).toHaveBeenCalledWith({ id: 9, decision: 'confirm', value: { type: 'WHT', amount: '1200', reference: 'WHT on interest' } })
    const flags = screen.getByRole('region', { name: 'Issues to resolve' })
    expect(within(flags).getByRole('button', { name: /Resolved/ })).toBeDisabled()
    await userEvent.type(within(flags).getByRole('textbox', { name: 'How it was resolved' }), 'Client sent page 3')
    await userEvent.click(within(flags).getByRole('button', { name: /Resolved/ }))
    expect(m.resolve.mutate).toHaveBeenCalledWith({ id: 4, resolution: 'Client sent page 3' })
  })
})
