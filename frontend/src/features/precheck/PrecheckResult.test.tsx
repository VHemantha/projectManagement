import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PrecheckResult } from './PrecheckResult'
import { output } from './precheckFixture'
import type { PrecheckOutput } from '@/api/precheck'
import { TooltipProvider } from '@/design-system'

const mocks = vi.hoisted(() => ({
  // A save that succeeds closes the form, as the real mutation's onSuccess does.
  teach: vi.fn((_payload: unknown, options?: { onSuccess?: () => void }) => options?.onSuccess?.()),
  setStatus: vi.fn(),
  lessons: undefined as unknown,
}))

vi.mock('@/api/precheck', () => ({
  useLessons: () => ({ data: mocks.lessons }),
  useTeachLesson: () => ({ mutate: mocks.teach, isPending: false, isError: false }),
  useSetLessonStatus: () => ({ mutate: mocks.setStatus }),
}))

function renderIt(o: PrecheckOutput = output) {
  return render(
    <TooltipProvider>
      <PrecheckResult output={o} jobKey="SMITH-1" />
    </TooltipProvider>,
  )
}

describe('PrecheckResult', () => {
  beforeEach(() => {
    mocks.teach.mockClear()
    mocks.setStatus.mockClear()
    mocks.lessons = undefined
  })

  it('shows the key documents, the business nature with its reasoning, and every request with its reason', () => {
    renderIt()
    const keys = screen.getByRole('heading', { name: 'Key documents' }).parentElement!
    expect(within(keys).getAllByLabelText('Found')).toHaveLength(3)
    expect(within(keys).getByRole('link', { name: /Client Questionnaire 2026\.pdf/ })).toHaveAttribute('href', 'https://drive.example/cq')
    expect(screen.getByRole('heading', { name: /Business nature: Residential rental/ })).toBeInTheDocument()
    expect(screen.getByText(/let through Barfoot & Thompson/)).toBeInTheDocument()
    expect(screen.getByText('The ASB loan was refinanced in October 2025.')).toBeInTheDocument()
    const requests = screen.getByRole('heading', { name: 'Requests to send (2)' }).closest('section')!
    expect(within(requests).getByRole('heading', { name: 'ASB loan' })).toBeInTheDocument()
    expect(within(requests).getByText(/old loan closing statement/)).toBeInTheDocument()
    expect(within(requests).getByText(/figure not found in the documents/)).toBeInTheDocument()
    expect(screen.getByText('Already provided (1)')).toBeInTheDocument()
    expect(screen.getByText('Not needed (1)')).toBeInTheDocument()
    expect(screen.getByText('Interest is fully deductible from 1 April 2025.')).toBeInTheDocument()
    expect(screen.getByText(/Email to the client \(drafted, not sent\)/)).toBeInTheDocument()
    expect(screen.getByText(output.email.subject)).toBeInTheDocument()
    expect(screen.getByText(/Lessons applied: No home office/)).toBeInTheDocument()
  })

  it('teaches the pre-check from a correction, for this client or for every client of the type', async () => {
    renderIt()
    await userEvent.click(screen.getByRole('button', { name: 'Correct: Body corporate levy invoice' }))
    expect(screen.getByLabelText('What was wrong')).toHaveValue('not_needed')
    expect(screen.getByRole('button', { name: 'Save lesson' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/What the pre-check should do instead/), 'Standalone house: there is no body corporate.')
    await userEvent.click(screen.getByLabelText(/Apply to all residential rental clients/))
    await userEvent.click(screen.getByRole('button', { name: 'Save lesson' }))
    expect(mocks.teach).toHaveBeenCalledWith(
      { kind: 'not_needed', item: 'Body corporate levy invoice', note: 'Standalone house: there is no body corporate.', firm_wide: true },
      expect.anything(),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Something was missed' }))
    expect(screen.getByLabelText('What was wrong')).toHaveValue('missed')
  })

  it('a lead sees lessons waiting for approval', async () => {
    mocks.lessons = {
      can_approve: true, lessons: [],
      pending_firm_wide: [{ id: 9, scope: 'firm', status: 'pending', kind: 'not_needed', precheck_type: 'residential_rental', item: 'Bank confirmation',
        note: 'Statements cover the year: no confirmation letter.', created_by: 'Pat', created_at: '', task: 'JONES-2' }],
    }
    renderIt()
    expect(screen.getByRole('heading', { name: 'Lessons waiting for approval (1)' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Apply to all clients' }))
    expect(mocks.setStatus).toHaveBeenCalledWith({ id: 9, status: 'active' })
  })

  it('blocked: says what is missing and shows the email for it', () => {
    renderIt({
      ...output, decision: { state: 'blocked', label: 'Blocked', reason: 'The pre-check cannot start without client questionnaire.' }, business_nature: null,
      key_documents: [{ role: 'questionnaire', label: 'Client questionnaire', found: false, note: '', files: [] }, ...output.key_documents.slice(1)],
      requests: [{ group: 'To start the pre-check', item: 'Your completed client questionnaire', decision: 'request', reason: 'It tells us what changed this year.', sources: [], documents: [], flags: [] }],
      provided: [], not_needed: [], preparer_notes: [], lessons_applied: [],
    })
    expect(screen.getByLabelText('Missing')).toBeInTheDocument()
    expect(screen.getByText('Not in the folder')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Something was missed' })).not.toBeInTheDocument()
    expect(screen.getByText('Your completed client questionnaire')).toBeInTheDocument()
  })
})
