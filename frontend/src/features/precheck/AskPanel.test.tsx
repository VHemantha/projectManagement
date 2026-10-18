import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AskPanel } from './AskPanel'
import type { AssistantQuestion } from '@/api/ask'

const mocks = vi.hoisted(() => ({
  questions: [] as unknown[],
  ask: vi.fn((_q: string, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
}))

vi.mock('@/api/ask', () => ({
  useConversation: () => ({ data: { questions: mocks.questions }, isLoading: false, isError: false }),
  useAsk: () => ({ mutate: mocks.ask, isPending: false, isError: false }),
}))

function q(over: Partial<AssistantQuestion>): AssistantQuestion {
  return {
    id: 'q1', question: 'How much was 43 Te Wharo Drive sold for?', status: 'answered', answer: 'It sold for $891,000.00 and settled on 1 October 2025.',
    answer_status: 'answered', flags: [], failure_reason: '', asked_by: 'Pat', created_at: '', answered_at: '',
    sources: [{ id: 'K1', label: 'Settlement Statement.pdf, page 1', how: 'words "Settlement"',
                evidence: { file_name: 'Settlement Statement.pdf', location: 'page 1', quote: 'Purchase price 891,000.00', drive_url: 'https://drive.example/s' } }],
    ...over,
  }
}

describe('AskPanel', () => {
  beforeEach(() => {
    mocks.ask.mockClear()
    mocks.questions = []
  })

  it('offers questions to start with, and asks one with Enter', async () => {
    render(<AskPanel jobKey="LANDM-1" />)
    await userEvent.click(screen.getByRole('button', { name: /What changed this year/ }))
    expect(mocks.ask).toHaveBeenCalledWith('What changed this year according to the questionnaire?', expect.anything())
    await userEvent.type(screen.getByLabelText('Your question'), 'Who manages the property?{Enter}')
    expect(mocks.ask).toHaveBeenLastCalledWith('Who manages the property?', expect.anything())
  })

  it('shows each answer with how sure it is and the passages it rests on', () => {
    mocks.questions = [
      q({}),
      q({ id: 'q2', question: 'What was the gross rent?', answer: 'Not in the passages.', answer_status: 'not_found', sources: [] }),
      q({ id: 'q3', question: 'Is the fee 3,000?', answer: 'It was 3,000.', answer_status: 'partial', flags: ['figure_not_in_documents'], sources: [] }),
      q({ id: 'q4', question: 'And the GST?', status: 'pending', answer: '', answer_status: '', sources: [] }),
    ]
    render(<AskPanel jobKey="LANDM-1" />)
    const items = within(screen.getByRole('list', { name: 'Questions and answers' })).getAllByRole('listitem').filter((li) => li.parentElement?.tagName === 'OL')
    expect(within(items[0]).getByText('Answered from the documents')).toBeInTheDocument()
    expect(within(items[0]).getByRole('link', { name: /Settlement Statement\.pdf, page 1/ })).toHaveAttribute('href', 'https://drive.example/s')
    expect(within(items[0]).getByText('exact match')).toBeInTheDocument()
    expect(within(items[1]).getByText('Not found in the documents')).toBeInTheDocument()
    expect(within(items[2]).getByText(/mentions a figure not found/)).toBeInTheDocument()
    expect(within(items[3]).getByText('Looking…')).toBeInTheDocument()
    expect(screen.getByText(/looking through the task/)).toBeInTheDocument()
  })

  it('labels each point by where it comes from, and says when the advice goes beyond NZ standards', () => {
    mocks.questions = [
      q({ question: 'Is the gain on sale taxable?', answer: 'Probably, under the bright-line test.', beyond_nz: true, outside_job: false, sources: [],
          points: [
            { text: 'The property settled on 1 October 2025.', basis: 'task_documents', reference: '', flags: [], sources: q({}).sources },
            { text: 'The bright-line test may tax the gain.', basis: 'nz_standards_law', reference: 'Income Tax Act 2007, s CB 6AA', flags: [], sources: [] },
            { text: 'In Australia a CGT discount would apply.', basis: 'general_knowledge', reference: 'Australian Income Tax Assessment Act 1997', flags: [], sources: [] },
          ] }),
      q({ id: 'q2', question: 'What is IFRS 16 about?', answer: 'Leases.', outside_job: true, beyond_nz: false, sources: [],
          points: [{ text: 'NZ IFRS 16 sets out lease accounting.', basis: 'nz_standards_law', reference: 'NZ IFRS 16', flags: [], sources: [] }] }),
    ]
    render(<AskPanel jobKey="LANDM-1" />)
    const conversation = screen.getByRole('list', { name: 'Questions and answers' })
    const [first, second] = Array.from(conversation.children) as HTMLElement[]
    expect(within(first).getByRole('note')).toHaveTextContent(/goes beyond NZ standards and law/)
    const points = within(within(first).getByRole('list', { name: 'Points of the answer' })).getAllByRole('listitem').filter((li) => li.parentElement?.tagName === 'OL')
    expect(points[0]).toHaveTextContent("From this task's documents")
    expect(within(points[0]).getByRole('link', { name: /Settlement Statement/ })).toBeInTheDocument()
    expect(points[1]).toHaveTextContent('NZ standards / law')
    expect(points[1]).toHaveTextContent('Source: Income Tax Act 2007, s CB 6AA')
    expect(points[2]).toHaveTextContent('General knowledge — beyond NZ standards')
    expect(points[2]).toHaveTextContent('Source: Australian Income Tax Assessment Act 1997')
    expect(within(first).getByText('Answered')).toBeInTheDocument()
    expect(within(second).getByText('Outside this job')).toBeInTheDocument()
    expect(within(second).queryByRole('note')).not.toBeInTheDocument()
  })
})
