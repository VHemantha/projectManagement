import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AiAssistant } from './Shared'
import type { AiMessage } from '@/api/localTax'

const m = vi.hoisted(() => ({
  decide: { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown, variables: undefined as unknown },
  ask: { mutate: vi.fn(), isPending: false, isError: false, error: null },
  messages: [] as unknown[],
}))
vi.mock('@/api/localTax', async (orig) => ({
  ...(await orig<typeof import('@/api/localTax')>()),
  useMessages: () => ({ data: { messages: m.messages, extractions: [] }, isLoading: false }),
  useAskLocalTax: () => m.ask,
  useClientChange: () => m.decide,
}))

const reply: AiMessage = {
  id: 7, role: 'ai', text: 'Here is what I would change.', by: '', at: '',
  data: {
    changes: [
      { n: 0, type: 'field', target: 'address', value: '12 Galle Road', label: 'Address', from: '1 Main Street', to: '12 Galle Road', reason: 'The client moved.',
        status: 'proposed' },
      { n: 1, type: 'journal', target: 'Rent corrected', value: '6100 | =1200000; 2110 | balance', label: 'Rent corrected', from: '', to: '',
        reason: 'Rent was 1.2 million.', status: 'proposed', lines: [
          { code: '6100', name: 'Rent', heading: 'admin_expenses', amount: '200000.00', sets: '1200000.00', was: '1000000.00' },
          { code: '2110', name: 'Accruals', heading: 'trade_payables', amount: '-200000.00' }] },
      { n: 2, type: 'note', target: 'events', value: 'None.', label: 'Note: Events after the reporting period', from: '', to: 'None.', reason: 'Confirmed.',
        status: 'applied', result: 'Note wording changed.', by: 'Pat' },
    ],
    changes_dropped: ['“entity_type” isn\'t client information the assistant can change.'],
  },
}

describe("a client's change request through the AI Assistant (AFIT, 26 Nov 2026)", () => {
  beforeEach(() => {
    m.decide.mutate = vi.fn()
    m.messages = [{ id: 6, role: 'person', text: 'The client says rent was 1.2 million and they moved.', data: {}, by: 'Pat', at: '' }, reply]
  })

  it('shows each change with what it changes, the journal worked out by code, and applies or dismisses one at a time', async () => {
    render(<AiAssistant taskKey="LOC-1" lead="Ask anything." />)
    expect(screen.getByPlaceholderText(/pass on the client's request/)).toBeInTheDocument()
    const list = screen.getByRole('generic', { name: 'Changes the client asked for' })
    const address = within(list).getByRole('region', { name: 'Address' })
    expect(within(address).getByText('1 Main Street')).toBeInTheDocument()
    expect(within(address).getByText('12 Galle Road')).toBeInTheDocument()
    const journal = within(list).getByRole('table', { name: 'Journal: Rent corrected' })
    expect(within(journal).getAllByText('200,000')).toHaveLength(2)  // the debit and the balancing credit
    expect(within(journal).getByText(/balance 1,000,000 → 1,200,000/)).toBeInTheDocument()
    // a journal is proposed for approval, not posted
    expect(within(list).getByRole('button', { name: 'Apply: Rent corrected' })).toHaveTextContent('Propose for approval')
    await userEvent.click(within(list).getByRole('button', { name: 'Apply: Address' }))
    expect(m.decide.mutate).toHaveBeenCalledWith({ message: 7, n: 0, decision: 'apply' })
    await userEvent.click(within(list).getByRole('button', { name: 'Dismiss: Rent corrected' }))
    expect(m.decide.mutate).toHaveBeenLastCalledWith({ message: 7, n: 1, decision: 'dismiss' })
    // done ones show who applied them; what TASKO can't make is said
    expect(within(list).getByText(/Note wording changed\. — Pat/)).toBeInTheDocument()
    expect(within(list).queryByRole('button', { name: /Note: Events/ })).toBeNull()
    expect(within(list).getByText(/Left out/)).toHaveTextContent('entity_type')
  })
})
