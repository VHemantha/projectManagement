import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReviewPanel } from './ReviewPanel'
import type { ReviewFindingRecord, ReviewState } from '@/api/review'

const mocks = vi.hoisted(() => ({
  data: undefined as unknown,
  run: vi.fn(),
  save: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  respond: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  missed: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  complete: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  setStatus: vi.fn(),
  lessons: { lessons: [] as unknown[], pending_firm_wide: [] as unknown[], can_approve: false },
}))

vi.mock('@/api/precheck', () => ({
  useLessons: () => ({ data: mocks.lessons }),
  useSetLessonStatus: () => ({ mutate: mocks.setStatus }),
  useTeachLesson: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

const mutation = (fn: unknown) => ({ mutate: fn, isPending: false, isError: false })
vi.mock('@/api/review', () => ({
  useJobReview: () => ({ data: mocks.data, isLoading: false, isError: false }),
  useRunReview: () => mutation(mocks.run),
  useSaveAssumption: () => mutation(mocks.save),
  useRespondToFinding: () => mutation(mocks.respond),
  useAddMissed: () => mutation(mocks.missed),
  useCompleteReview: () => mutation(mocks.complete),
}))

function finding(over: Partial<ReviewFindingRecord>): ReviewFindingRecord {
  return {
    id: 1, ref: 'R1', origin: 'ai', area: 'Comparatives', fs_line: 'Repairs and maintenance', issue: 'The comparative 2,410 does not agree to 2,140.',
    why: 'Opening figures must agree to the signed statements.', action: 'Correct the comparative.', severity: 'high',
    sources: [{ id: 'C1', label: 'Check: comparative', evidence_id: 'E-1' }], assumptions: [], flags: [], status: 'open', resolved_reason: '',
    response: '', note: '', responded_by: '', responded_at: null, responses: [], created_by: '', created_at: '', ...over,
  }
}

function state(over: Partial<ReviewState> = {}): ReviewState {
  return {
    session: { status: 'in_progress', completed_by: '', completed_at: null, note: '' },
    assumptions: [{
      id: 5, ref: 'A1', area: 'expenses', area_label: 'Expenses', fs_line: 'Repairs and maintenance', amount: '9850.00',
      judgement: 'Hot water cylinder treated as a repair.', basis: 'Like-for-like.', evidence: 'Kauri Plumbing invoice', status: 'active',
      history: [], created_by: 'Pat', updated_by: 'Pat', updated_at: '',
    }],
    findings: [finding({}), finding({ id: 2, ref: 'R2', severity: 'low', issue: 'Show rent by property.', status: 'closed', response: 'not_an_issue', note: 'One property.', responded_by: 'Rita' })],
    latest: {
      run_id: 'r', kind: 'review', status: 'complete', progress: [], failure_reason: '',
      review: {
        decision: { state: 'findings', label: 'Findings to address', reason: '1 finding open' }, summary: 'The comparative for repairs is wrong.',
        draft_fs: [{ name: 'Smith 2026 Draft Financial Statements.pdf', evidence_id: null }], draft_found_by: 'folder',
        findings: [], resolved: [], lessons_applied: [], counts: { high: 1, medium: 0, low: 0 },
        assumption_reviews: [{ assumption: 'A1', verdict: 'challenged', reason: 'A whole new cylinder replaces the asset.', sources: [] }],
        checks: [{ label: 'Comparative for Repairs agrees', passed: false, detail: 'draft 2,410; last year 2,140' }],
        evidence: { 'E-1': { file_name: 'Draft.pdf', location: 'line 7', quote: 'Repairs 9,850 2,410', drive_url: 'https://drive.example/d' } },
      },
    } as unknown as ReviewState['latest'],
    rounds: [], open_high: 1, can_complete: true, rounds_done: 1,
    areas: [{ value: 'expenses', label: 'Expenses' }, { value: 'other', label: 'Other' }],
    ...over,
  }
}

describe('ReviewPanel', () => {
  beforeEach(() => {
    for (const fn of [mocks.run, mocks.save, mocks.respond, mocks.missed, mocks.complete, mocks.setStatus]) fn.mockClear()
    mocks.data = state()
    mocks.lessons = { lessons: [], pending_firm_wide: [], can_approve: false }
  })

  it('shows the round, the open findings with their evidence, and the AI verdict on each assumption', async () => {
    render(<ReviewPanel jobKey="SMITH-1" />)
    expect(screen.getByText('Findings to address')).toBeInTheDocument()
    expect(screen.getByText('The comparative for repairs is wrong.')).toBeInTheDocument()
    expect(screen.getByText(/Reviewed: Smith 2026 Draft Financial Statements\.pdf/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open (1)' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('The comparative 2,410 does not agree to 2,140.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Check: comparative/ })).toHaveAttribute('href', 'https://drive.example/d')
    expect(screen.queryByText('Show rent by property.')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Closed (1)' }))
    expect(screen.getByText('Show rent by property.')).toBeInTheDocument()
    expect(screen.getByText(/Not an issue — Rita: One property\./)).toBeInTheDocument()
    expect(screen.getByText('Challenged')).toBeInTheDocument()
    expect(screen.getByText(/AI: A whole new cylinder replaces the asset\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run round 2' })).toBeEnabled()
  })

  it('a response that closes or corrects a finding needs a reason the AI can learn from', async () => {
    render(<ReviewPanel jobKey="SMITH-1" />)
    const group = screen.getByRole('group', { name: 'Respond to R1' })
    await userEvent.click(within(group).getByRole('button', { name: 'Agree' }))
    expect(mocks.respond).toHaveBeenCalledWith({ id: 1, response: 'agree', note: '' }, expect.anything())
    await userEvent.click(within(group).getByRole('button', { name: 'Not an issue' }))
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Why is it not an issue/), 'The partner accepted it.')
    await userEvent.selectOptions(screen.getByLabelText('Teach this to'), 'project')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.respond).toHaveBeenLastCalledWith({ id: 1, response: 'not_an_issue', note: 'The partner accepted it.', scope: 'project' }, expect.anything())
  })

  it('records an assumption and something the AI missed', async () => {
    render(<ReviewPanel jobKey="SMITH-1" />)
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    const form = screen.getByRole('form', { name: 'New assumption' })
    await userEvent.selectOptions(within(form).getByLabelText('Area'), 'expenses')
    await userEvent.type(within(form).getByLabelText('Statement line'), 'Home office')
    await userEvent.type(within(form).getByLabelText('Assumption or judgement'), 'Home office is 12% of the house.')
    await userEvent.click(within(form).getByRole('button', { name: 'Add assumption' }))
    expect(mocks.save).toHaveBeenCalledWith(
      { id: undefined, body: { area: 'expenses', fs_line: 'Home office', amount: '', judgement: 'Home office is 12% of the house.', basis: '', evidence: '' } },
      expect.anything(),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Withdraw' }))
    expect(mocks.save).toHaveBeenLastCalledWith({ id: 5, body: { status: 'withdrawn' } })

    await userEvent.click(screen.getByRole('button', { name: /Something the AI missed/ }))
    const missed = screen.getByRole('form', { name: 'Something the AI missed' })
    await userEvent.type(within(missed).getByLabelText('What was missed'), 'GST on the sale is not accounted for.')
    await userEvent.click(within(missed).getByRole('button', { name: 'Add finding' }))
    expect(mocks.missed).toHaveBeenCalledWith({ area: '', fs_line: '', issue: 'GST on the sale is not accounted for.', note: '', scope: 'client' }, expect.anything())
  })

  it('completing with a high finding open needs a note; a completed review is locked until reopened', async () => {
    const { unmount } = render(<ReviewPanel jobKey="SMITH-1" />)
    await userEvent.click(screen.getByRole('button', { name: 'Complete review' }))
    expect(screen.getByText(/1 high finding is still open/)).toBeInTheDocument()
    const submit = screen.getAllByRole('button', { name: 'Complete review' }).at(-1)!
    expect(submit).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Completion note/), 'Partner accepted the difference.')
    await userEvent.click(submit)
    expect(mocks.complete).toHaveBeenCalledWith({ note: 'Partner accepted the difference.' }, expect.anything())
    unmount()

    mocks.data = state({ session: { status: 'complete', completed_by: 'Rita', completed_at: '', note: 'Done.' } })
    render(<ReviewPanel jobKey="SMITH-1" />)
    expect(screen.getByText(/Review complete — Rita/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Run round/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Respond to R1' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reopen review' }))
    expect(mocks.complete).toHaveBeenLastCalledWith({ reopen: true })
  })

  it('before any round: says how to start', () => {
    mocks.data = state({ latest: null, findings: [], rounds_done: 0, open_high: 0 })
    render(<ReviewPanel jobKey="SMITH-1" />)
    expect(screen.getByRole('button', { name: 'Run AI review' })).toBeEnabled()
    expect(screen.getByText('Run the AI review to see findings.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Complete review' })).toBeDisabled()
  })

  it('shows the rules learned from corrections, and a lead approves wider ones', async () => {
    mocks.lessons = {
      can_approve: true,
      lessons: [{ id: 4, scope: 'client', scope_label: 'This client', status: 'active', kind: 'not_needed', item: 'Rent by property', note: 'One property only.',
                  rule: { title: 'One property: rent in one line', when: 'The client owns one rental.', do: 'Do not split rent by property.', why: 'Nothing to split.' },
                  drafting: 'drafted', created_by: 'Rita', task: 'SMITH-1', precheck_type: '', created_at: '' },
                { id: 5, scope: 'client', scope_label: 'This client', status: 'active', kind: 'missed', item: 'GST on sale', note: 'Check GST on a sale.',
                  rule: null, drafting: 'drafting', created_by: 'Rita', task: 'SMITH-1', precheck_type: '', created_at: '' }],
      pending_firm_wide: [{ id: 6, scope: 'team', status: 'pending', kind: 'other', item: 'Bond', note: 'Ask for the bond receipt.', rule: null,
                            created_by: 'Sam', task: 'JONES-2', precheck_type: '', created_at: '' }],
    }
    render(<ReviewPanel jobKey="SMITH-1" />)
    expect(screen.getByRole('heading', { name: 'Learned rules (2)' })).toBeInTheDocument()
    expect(screen.getByText('One property: rent in one line')).toBeInTheDocument()
    expect(screen.getByText(/Do not split rent by property\./)).toBeInTheDocument()
    expect(screen.getByText(/drafting this as a rule; the note applies meanwhile/)).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'Switch off' })[0])
    expect(mocks.setStatus).toHaveBeenCalledWith({ id: 4, status: 'disabled' })
    await userEvent.click(screen.getByRole('button', { name: 'Approve for this workspace' }))
    expect(mocks.setStatus).toHaveBeenLastCalledWith({ id: 6, status: 'active' })
  })
})
