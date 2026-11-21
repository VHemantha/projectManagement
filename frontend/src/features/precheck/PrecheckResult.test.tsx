import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { classify } from './docKinds'
import { PrecheckResult } from './PrecheckResult'
import { output } from './precheckFixture'
import type { PrecheckOutput } from '@/api/precheck'
import { TooltipProvider } from '@/design-system'

const mocks = vi.hoisted(() => ({
  gaps: undefined as unknown,
  gapAction: vi.fn(),
  // A save that succeeds closes the form, as the real mutation's onSuccess does.
  teach: vi.fn((_payload: unknown, options?: { onSuccess?: () => void }) => options?.onSuccess?.()),
  run: vi.fn(),
  setStatus: vi.fn(),
  lessons: undefined as unknown,
  answers: [] as unknown[],
  answer: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  ask: vi.fn((_q: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
}))

vi.mock('@/api/precheck', () => ({
  useLessons: () => ({ data: mocks.lessons }),
  useJobGaps: () => ({ data: mocks.gaps }),
  useGapAction: () => ({ mutate: mocks.gapAction, isPending: false, isError: false, isSuccess: false }),
  useTeachLesson: () => ({ mutate: mocks.teach, isPending: false, isError: false }),
  useRunPrecheck: () => ({ mutate: mocks.run, isPending: false, isError: false }),
  useSetLessonStatus: () => ({ mutate: mocks.setStatus }),
  useAccountantAnswers: () => ({ data: { answers: mocks.answers } }),
  useAnswerQuestion: () => ({ mutate: mocks.answer, isPending: false, isError: false }),
}))

vi.mock('@/api/ask', () => ({
  useAsk: () => ({ mutate: mocks.ask, isPending: false, isError: false }),
}))
vi.mock('./PoliciesPanel', () => ({
  PolicyFeedbackForm: ({ policyId, context }: { policyId: number; context?: string }) => (
    <div>feedback form for policy {policyId} on {context}</div>
  ),
}))

function renderIt(o: PrecheckOutput = output, extra?: { chat?: React.ReactNode; information?: React.ReactNode }) {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <PrecheckResult output={o} jobKey="SMITH-1" {...extra} />
      </TooltipProvider>
    </MemoryRouter>,
  )
}

const lesson = (item: string, note: string) => ({
  id: 4, scope: 'client', status: 'active', kind: 'not_needed', precheck_type: 'residential_rental', item, note, created_by: 'Pat', created_at: '', task: 'SMITH-1',
})

describe('The pre-check result (AFIT wireframe, 19 Nov 2026)', () => {
  beforeEach(() => {
    mocks.teach.mockClear()
    mocks.run.mockClear()
    mocks.setStatus.mockClear()
    mocks.lessons = undefined
    mocks.answers = []
    mocks.answer.mockClear()
    window.localStorage.clear()
  })

  it('opens on the points: tallies, each point with its reason, status and supporting-document icons, beside the chat', () => {
    renderIt(output, { chat: <div>the agent chat</div> })
    expect(screen.getByRole('tab', { name: 'Pre-Check Results (Points)' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Pre-Check Results (Points)', 'Snapshot', 'Your Information', 'AI to Human Questions'])
    const points = screen.getByRole('heading', { name: 'Pre-Check Results (Points)' }).closest('section')!
    expect(within(points).getByText('Total points', { selector: 'dt' }).nextSibling).toHaveTextContent('2')
    expect(within(points).getByText('To review', { selector: 'dt' }).nextSibling).toHaveTextContent('2')
    expect(within(points).getByText('Corrected', { selector: 'dt' }).nextSibling).toHaveTextContent('0')
    const rows = within(points).getAllByRole('listitem')
    expect(within(rows[0]).getByRole('button', { name: 'Refinancing documents' })).toBeInTheDocument()
    expect(rows[0]).toHaveTextContent('we need the old loan closing statement')
    expect(within(rows[0]).getByText('To review')).toBeInTheDocument()
    // A reference is its document's icon: the questionnaire (CQ); last year's trial balance (TB).
    expect(within(rows[0]).getByRole('img', { name: /^Client questionnaire: Questionnaire: Did you refinance/ })).toHaveTextContent('CQ')
    expect(within(rows[1]).getByRole('img', { name: /^Trial balance: / })).toHaveTextContent('TB')
    expect(screen.getByText('the agent chat')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Learning & Continuous Improvement' })).toBeInTheDocument()
    expect(screen.getByText('Applied in this run: No home office when every property is managed.')).toBeInTheDocument()
    // What is provided or not needed is folded below the points.
    expect(screen.getByText('Already provided (1)').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Not needed (1)').closest('details')).not.toHaveAttribute('open')
  })

  it('a point opens to its details, the comment box and what the AI will do', async () => {
    renderIt()
    await userEvent.click(screen.getByRole('button', { name: 'Show details: Body corporate levy invoice' }))
    const row = screen.getByRole('button', { name: 'Body corporate levy invoice' }).closest('li')!
    expect(within(row).getByText('12 Kauri Street')).toBeInTheDocument()
    expect(within(row).getByText(/a figure not found in the documents/)).toBeInTheDocument()
    expect(within(row).getByRole('heading', { name: 'Your comment / correction' })).toBeInTheDocument()
    expect(within(row).getByRole('heading', { name: 'AI action (auto-update)' })).toBeInTheDocument()
    expect(row).toHaveTextContent('the request list and the client email follow it on the next run')
  })

  it('says what the policy check did, with the policy behind each change and a way to give feedback on it (AFIT, 20 Nov 2026)', async () => {
    const policy = { id: 9, title: 'Sold rentals: settlement statement only', scope_label: 'Group: Smith group' }
    const changed: PrecheckOutput = {
      ...output,
      requests: [
        { ...output.requests[0], policy: { changed: false, policies: [policy] } },
        { ...output.requests[1], policy: { changed: true, policies: [policy], note: 'Sold rentals need only the settlement statement.',
          was: { decision: 'not_needed', label: 'not needed', priority: 'normal', reason: 'Standalone house.' } } },
      ],
      policy_check: { checked: 5, changed: 1, added: 0, policies: [{ ...policy, text: 'Ask only for…', scope: 'group', applied_to: 2 }] },
    }
    renderIt(changed)
    expect(screen.getByRole('note')).toHaveTextContent('Every point was checked against 1 pre-check policy for this task: 1 changed, 0 added.')
    expect(screen.getByRole('link', { name: 'See the policies' })).toHaveAttribute('href', '/ai-rules?tab=policies')
    const row = screen.getByRole('button', { name: 'Body corporate levy invoice' }).closest('li')!
    expect(within(row).getByText('Changed by a policy')).toBeInTheDocument()
    await userEvent.click(within(row).getByRole('button', { name: 'Show details: Body corporate levy invoice' }))
    expect(row).toHaveTextContent('Changed to follow a policy: Sold rentals need only the settlement statement.')
    expect(row).toHaveTextContent('Before: not needed — Standalone house.')
    await userEvent.click(within(row).getByRole('button', { name: 'Feedback on the policy Sold rentals: settlement statement only' }))
    expect(within(row).getByText(/feedback form for policy 9 on Body corporate levy invoice/)).toBeInTheDocument()
  })

  it('asks the chat about one point, naming it so the agent answers about that point (AFIT, 20 Nov 2026)', async () => {
    renderIt()
    await userEvent.click(screen.getByRole('button', { name: 'Show details: Refinancing documents' }))
    await userEvent.click(screen.getByRole('button', { name: 'Ask the agent about this point' }))
    const input = screen.getByLabelText(/Your question about “Refinancing documents”/)
    await userEvent.clear(input)
    await userEvent.type(input, 'Which loan is this?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(mocks.ask).toHaveBeenCalledWith('About the pre-check point "Refinancing documents": Which loan is this?', expect.anything())
    expect(screen.getByText(/Asked. The answer appears in the chat./)).toBeInTheDocument()
  })

  it('a correction is saved as a lesson, for this client or every client of the type, and can re-run the pre-check', async () => {
    renderIt()
    await userEvent.click(screen.getByRole('button', { name: 'Correct: Body corporate levy invoice' }))
    expect(screen.getByLabelText('What was wrong')).toHaveValue('not_needed')
    expect(screen.getByRole('button', { name: 'Save lesson' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/What the pre-check should do instead/), 'Standalone house: there is no body corporate.')
    // The type of check it is for starts at this run's business nature (AFIT, 29 Oct 2026).
    expect(screen.getByLabelText('Type of check')).toHaveValue('residential_rental')
    await userEvent.selectOptions(screen.getByLabelText('Entity type'), 'trust')
    await userEvent.click(screen.getByLabelText(/Apply to every client: each residential rental check of a Trust/))
    await userEvent.click(screen.getByRole('button', { name: /Save and re-run/ }))
    expect(mocks.teach).toHaveBeenCalledWith(
      { kind: 'not_needed', item: 'Body corporate levy invoice', note: 'Standalone house: there is no body corporate.', firm_wide: true,
        precheck_type: 'residential_rental', entity_type: 'trust' },
      expect.anything(),
    )
    expect(mocks.run).toHaveBeenCalled()
    const row = screen.getByRole('button', { name: 'Body corporate levy invoice' }).closest('li')!
    expect(within(row).getByText('Corrected')).toBeInTheDocument()
    expect(row).toHaveTextContent('Re-running the pre-check: the request list and the email update when it finishes.')
    await userEvent.click(screen.getByRole('button', { name: /Something was missed/ }))
    expect(screen.getByLabelText('What was wrong')).toHaveValue('missed')
  })

  it("a point someone corrected shows as corrected, with that person's comment", async () => {
    mocks.lessons = { can_approve: false, pending_firm_wide: [], lessons: [lesson('Body corporate levy invoice', 'Standalone house: no body corporate.')] }
    renderIt()
    const points = screen.getByRole('heading', { name: 'Pre-Check Results (Points)' }).closest('section')!
    expect(within(points).getByText('Corrected', { selector: 'dt' }).nextSibling).toHaveTextContent('1')
    expect(within(points).getByText('To review', { selector: 'dt' }).nextSibling).toHaveTextContent('1')
    await userEvent.click(screen.getByRole('button', { name: /View comment/ }))
    expect(screen.getByText('Standalone house: no body corporate.')).toBeInTheDocument()
    expect(screen.getByText('1 correction is kept as learning for this client.')).toBeInTheDocument()
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

  it('the client email is drafted from the points: edited, kept as a draft, previewed, or opened in an email app', async () => {
    renderIt()
    const email = screen.getByRole('region', { name: 'Email to the client' })
    expect(within(email).getByText(output.email.subject)).toBeInTheDocument()
    expect(within(email).getByText('Drafted from the points')).toBeInTheDocument()
    const send = within(email).getByRole('link', { name: /Send to client/ })
    expect(send.getAttribute('href')).toBe(`mailto:?subject=${encodeURIComponent(output.email.subject)}&body=${encodeURIComponent(output.email.body)}`)
    await userEvent.click(within(email).getByRole('button', { name: /Edit/ }))
    const message = within(email).getByLabelText('Message')
    await userEvent.clear(message)
    await userEvent.type(message, 'Hi John, a short list.')
    await userEvent.click(within(email).getByRole('button', { name: /Save as draft/ }))
    expect(within(email).getByText('Draft saved in this browser.')).toBeInTheDocument()
    expect(within(email).getByText('Edited by you')).toBeInTheDocument()
    expect(within(email).getByRole('link', { name: /Send to client/ }).getAttribute('href')).toContain(encodeURIComponent('Hi John, a short list.'))
    await userEvent.click(within(email).getByRole('button', { name: /Preview/ }))
    expect(within(screen.getByRole('dialog', { name: 'Email preview' })).getByText('Hi John, a short list.')).toBeInTheDocument()
  })

  it('blocked: says what is missing, under your information, and the email asks for it', async () => {
    renderIt({
      ...output, decision: { state: 'blocked', label: 'Blocked', reason: 'The pre-check cannot start without client questionnaire.' }, business_nature: null,
      key_documents: [{ role: 'questionnaire', label: 'Client questionnaire', found: false, note: '', files: [] }, ...output.key_documents.slice(1)],
      requests: [{ group: 'To start the pre-check', item: 'Your completed client questionnaire', decision: 'request', reason: 'It tells us what changed this year.', sources: [], documents: [], flags: [] }],
      provided: [], not_needed: [], preparer_notes: [], lessons_applied: [],
    })
    expect(screen.getByText('Your completed client questionnaire')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Something was missed/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Your Information' }))
    expect(screen.getByLabelText('Missing')).toBeInTheDocument()
    expect(screen.getByText('Not in the folder')).toBeInTheDocument()
  })

  it('a missing key document is requested first, as a plain note rather than a warning', async () => {
    renderIt({
      ...output,
      requests: [
        { group: 'Key documents', item: 'Your completed client questionnaire for the year to 31 March 2026', decision: 'request',
          reason: 'It tells us what changed this year.', sources: [], documents: [], flags: ['key_document'] },
        ...output.requests,
      ],
    })
    await userEvent.click(screen.getByRole('button', { name: 'Your completed client questionnaire for the year to 31 March 2026' }))
    expect(screen.getByText('Not in the folder: requested first.')).toBeInTheDocument()
    expect(screen.queryByText(/key_document/)).not.toBeInTheDocument()
  })

  it('the AI to human questions are answered in place, apart from the client requests, and counted until answered', async () => {
    const question = { group: 'Related parties', item: "Does the firm prepare Smith Holdings' accounts?", decision: 'ask_accountant' as const,
                       priority: 'blocking' as const, reason: 'Decides whether to ask the client.', sources: [], documents: [], flags: [] }
    renderIt({ ...output, accountant_questions: [question] })
    expect(screen.getByRole('tab', { name: /AI to Human Questions/ })).toHaveTextContent('1 open')
    expect(screen.queryByText(/Smith Holdings/)).not.toBeInTheDocument() // not among the client's points
    await userEvent.click(screen.getByRole('tab', { name: /AI to Human Questions/ }))
    const b = screen.getByRole('heading', { name: 'Section B — Internal analysis and accountant questions' }).closest('section')!
    expect(within(b).getByText("Does the firm prepare Smith Holdings' accounts?")).toBeInTheDocument()
    expect(within(b).getByText('Interest is fully deductible from 1 April 2025.')).toBeInTheDocument()
    await userEvent.click(within(b).getByRole('button', { name: "Answer: Does the firm prepare Smith Holdings' accounts?" }))
    await userEvent.type(within(b).getByLabelText(/Your answer/), 'Yes, we prepare them: use our file.')
    await userEvent.click(within(b).getByRole('button', { name: 'Save answer' }))
    expect(mocks.answer).toHaveBeenCalledWith({ question: "Does the firm prepare Smith Holdings' accounts?", answer: 'Yes, we prepare them: use our file.' }, expect.anything())
  })

  it('shows an earlier answer instead of asking again', async () => {
    mocks.answers = [{ id: 1, question: 'Is a dividend intended?', answer: 'No dividend this year.', answered_by: 'Rita', answered_at: '' }]
    renderIt({ ...output, accountant_questions: [{ group: 'Dividends', item: 'Is a dividend intended?', decision: 'ask_accountant', reason: 'Paid last year.', sources: [], documents: [], flags: [] }] })
    expect(screen.getByRole('tab', { name: /AI to Human Questions/ })).not.toHaveTextContent('open')
    await userEvent.click(screen.getByRole('tab', { name: /AI to Human Questions/ }))
    expect(screen.getByText(/Answered by Rita:/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Answer:/ })).not.toBeInTheDocument()
  })

  it('your information: the key documents as icons, the business nature, and the run details given to it', async () => {
    renderIt(output, { information: <p>how the AI got here</p> })
    await userEvent.click(screen.getByRole('tab', { name: 'Your Information' }))
    const keys = screen.getByRole('heading', { name: 'Key documents' }).closest('section')!
    expect(within(keys).getByRole('link', { name: /Client questionnaire: Client Questionnaire 2026\.pdf, line 3/ })).toHaveAttribute('href', 'https://drive.example/cq')
    expect(screen.getByRole('region', { name: 'Business nature' })).toHaveTextContent('Business nature: Residential rental')
    expect(screen.getByText('The ASB loan was refinanced in October 2025.')).toBeInTheDocument()
    expect(screen.getByText('how the AI got here')).toBeInTheDocument()
  })
})

describe('Supporting-document icons (AFIT reference icons, 19 Nov 2026)', () => {
  const ev = {
    a: { file_name: 'Smith 2025 Financial Statements - Signed.pdf', location: 'page 2', quote: '', drive_url: '' },
    b: { file_name: 'ANZ 01-0123-0456789-00 statement FY26.pdf', location: '', quote: '', drive_url: '' },
    c: { file_name: 'Tower Insurance policy schedule.pdf', location: '', quote: '', drive_url: '' },
    d: { file_name: 'Xero General Ledger Detail 2026.xlsx', location: '', quote: '', drive_url: '' },
  }
  it('each source is named by what it is and its year', () => {
    expect(classify({ id: 'F3', label: "Last year's statements: Rental income", evidence_id: 'a' }, ev)).toMatchObject({ kind: 'FS', year: 'FY25' })
    expect(classify({ id: 'D4', label: 'ANZ statement', evidence_id: 'b' }, ev)).toMatchObject({ kind: 'BANK', year: 'FY26' })
    expect(classify({ id: 'R9', label: 'Received: Tower Insurance policy schedule.pdf', evidence_id: 'c' }, ev)).toMatchObject({ kind: 'INS' })
    expect(classify({ id: 'G2', label: 'General ledger: Rates', evidence_id: 'd' }, ev)).toMatchObject({ kind: 'GL', year: 'FY26' })
    expect(classify({ id: 'SN1', label: 'Special note: sold in June', evidence_id: null }, ev)).toMatchObject({ kind: 'NOTE' })
    expect(classify({ id: 'D8', label: 'photo.jpg', evidence_id: null }, ev)).toMatchObject({ kind: 'SUP' })
  })
})
