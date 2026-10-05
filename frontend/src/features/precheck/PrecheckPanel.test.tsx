import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PrecheckPanel } from './PrecheckPanel'
import { costChip, trailStep } from './precheckText'
import type { Finding, JobPrecheck, PrecheckSetup, Run } from '@/api/precheck'
import { TooltipProvider } from '@/design-system'
import { output } from './precheckFixture'

const mocks = vi.hoisted(() => ({
  data: null as unknown,
  start: vi.fn(),
  save: vi.fn(),
  dispose: vi.fn(),
  draft: vi.fn(),
}))

vi.mock('@/api/precheck', () => ({
  useJobPrecheck: () => ({ data: mocks.data, isLoading: false, isError: false }),
  usePrecheckRun: () => ({ data: undefined }),
  useRunPrecheck: () => ({ mutate: mocks.start, isPending: false, isError: false }),
  useSavePrecheckSetup: () => ({ mutate: mocks.save, isPending: false, isError: false }),
  useSetDisposition: () => ({ mutate: mocks.dispose, isPending: false }),
  useDraftDirections: () => ({ mutate: mocks.draft, isPending: false, isError: false }),
  useLessons: () => ({ data: undefined }),
  useTeachLesson: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useSetLessonStatus: () => ({ mutate: vi.fn() }),
}))

const setup: PrecheckSetup = {
  drive_folder_url: 'https://drive.google.com/drive/folders/abc',
  drive_folder_id: 'abc',
  precheck_type: 'auto',
  precheck_types: [
    { value: 'auto', label: 'Decide from the questionnaire' },
    { value: 'residential_rental', label: 'Residential rental' },
    { value: 'general', label: 'General business' },
    { value: 'investment', label: 'Investment' },
  ],
  direction_items: [
    { id: 'D1', text: 'Agree the bank reconciliation' },
    { id: 'D2', text: 'Confirm accruals are complete' },
  ],
  missing: [],
  ready: true,
}

const finding = (o: Partial<Finding>): Finding => ({
  id: 1,
  finding_id: 'F1',
  direction_ref: 'none',
  area: 'Trade debtors',
  status: 'exception',
  severity: 'high',
  kind: 'rule',
  title: 'Debtors schedule does not agree to the trial balance',
  why: 'The schedule totals 112,400 but the trial balance shows 118,900.',
  source: 'rule',
  confidence: 'high',
  evidence: [
    { id: 'E1', file_name: 'Debtors schedule.xlsx', location: "sheet 'Debtors', row 4", quote: 'row 4: Total | 112400', drive_url: 'https://docs.google.com/spreadsheets/d/x/edit#range=A4' },
  ],
  disposition: null,
  ...o,
})

const run = (o: Partial<Run> = {}): Run => ({
  run_id: 'r1',
  status: 'complete',
  verdict: 'not_ready',
  summary: 'One schedule does not agree to the trial balance.',
  coverage: { addressed: 1, total: 2 },
  counts: { high: 1, medium: 1, low: 0 },
  created_at: '2026-10-02T09:00:00Z',
  finished_at: '2026-10-02T09:00:20Z',
  requested_by: 'Pat',
  demo: false,
  direction_items: [
    { id: 'D1', text: 'Agree the bank reconciliation', addressed: true },
    { id: 'D2', text: 'Confirm accruals are complete', addressed: false },
  ],
  trail: {
    read: { label: '14 documents, 3 changed since last run', detail: [{ name: 'TB.xlsx', kind: 'trial balance', changed: true, problem: '' }, { name: 'Receipt.jpg', kind: 'other', changed: false, problem: '', note: 'text read from the image by AI' }] },
    checked: { label: '22 rules run, 2 failed', detail: [{ label: 'Trial balance debits equal credits', passed: true, note: '' }] },
    compared: { label: '2 Direction Note items compared', detail: [] },
    judged: { label: '5 findings weighed, 3 kept', detail: [], findings_in: 5, findings_out: 3, escalated: 0, how: 'model' },
    verified: { label: '4 source passages linked', detail: [], evidence: 4, rejected_no_evidence: 1, rules_restored: 0, items_filled: 0 },
  },
  progress: [],
  skipped: [],
  failure_reason: '',
  usage: { totals: { input: 9000, output: 600, cache_read: 3000, cache_write: 0 }, cost_usd: 0.0123, cache_share: 0.25, model_calls: 4 },
  models: { reader: 'claude-haiku-4-5-20251001', judge: 'claude-sonnet-5-5' },
  duration_s: 20,
  findings: [
    finding({}),
    finding({ id: 2, finding_id: 'F2', severity: 'medium', status: 'unclear', kind: 'ai_suggestion', source: 'ai', confidence: 'low', direction_ref: 'D2', title: 'Accruals sign-off not evidenced', why: 'Who reviewed the accruals workpaper, and when?', evidence: [] }),
    finding({ id: 3, finding_id: 'F3', severity: 'low', status: 'addressed', kind: 'fact', source: 'ai', direction_ref: 'D1', title: 'Bank reconciled to the ledger', why: 'Both show 48,210.' }),
  ],
  ...o,
})

const panel = (latest: Run | null, s: PrecheckSetup = setup): JobPrecheck => ({ job: 'ACME-1', setup: s, latest, history: latest ? [latest] : [], draft: null })

beforeEach(() => {
  Object.values(mocks).forEach((m) => typeof m === 'function' && (m as ReturnType<typeof vi.fn>).mockClear())
})

describe('PrecheckPanel states', () => {
  it('not set up: asks for the folder and the Direction Note instead of inventing them', async () => {
    mocks.data = panel(null, { ...setup, drive_folder_url: '', drive_folder_id: '', direction_items: [], missing: ['drive_folder', 'direction_note'], ready: false })
    render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText(/needs its Google Drive folder/)).toBeInTheDocument()
    expect(screen.getByText(/client questionnaire with last year/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Run pre-check/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Draft with AI' })).not.toBeInTheDocument() // needs the folder first
    await userEvent.type(screen.getByLabelText(/Google Drive folder link/), 'https://drive.google.com/drive/folders/xyz')
    await userEvent.type(screen.getByLabelText(/Direction Note items/), 'Agree bank{Enter}Check accruals')
    await userEvent.selectOptions(screen.getByLabelText(/Pre-check type/), 'residential_rental')
    expect(screen.getByText(/Residential rental: properties, managers, loans/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(mocks.save).toHaveBeenCalledWith(
      {
        drive_folder_url: 'https://drive.google.com/drive/folders/xyz',
        direction_items: ['Agree bank', 'Check accruals'],
        precheck_type: 'residential_rental',
      },
      expect.anything(),
    )
  })

  it('never run: one button starts it', async () => {
    mocks.data = panel(null)
    render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText(/Not run yet/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Run pre-check' }))
    expect(mocks.start).toHaveBeenCalled()
  })

  it('running: the trail fills in live from events', () => {
    mocks.data = panel(run({
      status: 'running', verdict: '', trail: {}, findings: [],
      progress: [
        { stage: 'read', state: 'done', label: '14 documents, 3 changed since last run', counts: { documents: 14 } },
        { stage: 'checked', state: 'running', label: 'Running the automatic checks', counts: null },
      ],
    }))
    render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText('Checking the task…')).toBeInTheDocument()
    const steps = screen.getAllByRole('listitem')
    expect(steps.map((s) => s.getAttribute('data-state'))).toEqual(['done', 'running', 'waiting', 'waiting', 'waiting'])
    expect(steps[0]).toHaveTextContent('14 documents, 3 changed since last run')
    expect(screen.queryByRole('button', { name: /^Run (again|pre-check)$/ })).not.toBeInTheDocument() // one run at a time
  })

  it('complete: verdict in words, coverage, counts, grouped findings', () => {
    mocks.data = panel(run())
    render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText('Not ready')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '1 of 2 Direction Note items addressed' })).toBeInTheDocument()
    expect(screen.getByLabelText('Open findings by severity')).toHaveTextContent('1 high1 medium0 low')
    expect(screen.getByText('One schedule does not agree to the trial balance.')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['How the AI got here', 'Direction Note', 'High 1', 'Medium 1'])
    const cards = screen.getAllByRole('article')
    expect(within(cards[0]).getByText('Rule')).toBeInTheDocument()
    expect(within(cards[1]).getByText('AI suggestion')).toBeInTheDocument()
    expect(within(cards[1]).getByText('D2')).toBeInTheDocument()
    expect(within(cards[1]).getByLabelText('Confidence: low')).toBeInTheDocument()
    expect(within(cards[1]).getByText('No source: a question for a person')).toBeInTheDocument()
    const footer = screen.getByRole('contentinfo')
    expect(footer).toHaveTextContent('AI pre-check, not a human review')
    expect(footer).toHaveTextContent('claude-haiku-4-5-20251001 · claude-sonnet-5-5')
    expect(footer).toHaveTextContent('13k tokens · 25% from cache · $0.01')
  })

  it('a trail step opens to its detail', async () => {
    mocks.data = panel(run())
    render(<PrecheckPanel jobKey="ACME-1" />)
    const step = screen.getByRole('button', { name: /Checked/ })
    expect(step).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(step)
    expect(step).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Trial balance debits equal credits')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Sources linked/ }))
    expect(screen.getByText(/1 rejected for having no evidence/)).toBeInTheDocument()  // a run from before 5 Oct 2026
  })

  it('a finding opens to its quoted source with a Drive link', async () => {
    mocks.data = panel(run())
    render(<PrecheckPanel jobKey="ACME-1" />)
    await userEvent.click(screen.getByRole('button', { name: /Show the evidence for: Debtors schedule/ }))
    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByText('The claim')).toBeInTheDocument()
    expect(within(drawer).getByText('Debtors schedule.xlsx')).toBeInTheDocument()
    expect(within(drawer).getByText("sheet 'Debtors', row 4")).toBeInTheDocument()
    expect(within(drawer).getByText('row 4: Total | 112400').tagName).toBe('MARK')
    expect(within(drawer).getByRole('link', { name: /Open in Drive/ })).toHaveAttribute('href', 'https://docs.google.com/spreadsheets/d/x/edit#range=A4')
    expect(within(drawer).getByText('An automatic check (no AI)')).toBeInTheDocument()
  })

  it('a decision is one click and can be undone', async () => {
    mocks.data = panel(run())
    const { rerender } = render(<PrecheckPanel jobKey="ACME-1" />)
    await userEvent.click(within(screen.getAllByRole('article')[0]).getByRole('button', { name: 'Reject' }))
    expect(mocks.dispose).toHaveBeenCalledWith({ findingId: 1, disposition: 'rejected' })
    const decided = run()
    decided.findings[0].disposition = { disposition: 'rejected', by: 'Pat', at: '' }
    mocks.data = panel(decided)
    rerender(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText('Rejected by Pat')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Undo/ }))
    expect(mocks.dispose).toHaveBeenLastCalledWith({ findingId: 1, disposition: 'cleared' })
  })

  it('no Direction Note: the pre-check still runs, and a person can ask for a draft to edit', async () => {
    mocks.data = panel(null, { ...setup, direction_items: [], missing: ['direction_note'] })
    const { unmount } = render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText(/first looks for this year.s client questionnaire/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Run pre-check' }))
    expect(mocks.start).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Edit folder, type and instructions' }))
    await userEvent.click(screen.getByRole('button', { name: 'Draft with AI' }))
    expect(mocks.draft).toHaveBeenCalled()
    unmount()

    // While the draft is being written the button shows it; when it arrives, each item says why it is there.
    mocks.data = { ...panel(null, { ...setup, direction_items: [], missing: ['direction_note'] }), draft: { status: 'running', failure_reason: '', created_at: '' } }
    const second = render(<PrecheckPanel jobKey="ACME-1" />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit folder, type and instructions' }))
    expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled()
    second.unmount()

    mocks.data = panel(null, {
      ...setup,
      direction_items: [
        { id: 'D1', text: 'Agree the debtors schedule to the trial balance', origin: 'ai', reason: 'Accepted on last year\'s job.', basis: 'history' },
        { id: 'D2', text: 'Check the tax computation', origin: 'person', reason: '', basis: '' },
      ],
    })
    render(<PrecheckPanel jobKey="ACME-1" />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit folder, type and instructions' }))
    expect(screen.getByLabelText(/Direction Note items/)).toHaveValue('Agree the debtors schedule to the trial balance\nCheck the tax computation')
    const why = screen.getByText('Drafted by AI: why each item is here').parentElement!
    expect(why).toHaveTextContent('D1')
    expect(why).toHaveTextContent("From past tasks: Accepted on last year's job.")
    expect(why).not.toHaveTextContent('Check the tax computation')
  })

  it('the result shows the Direction Note as verified, and which items the AI drafted', () => {
    const r = run()
    r.direction_items = [
      { id: 'D1', text: 'Agree the bank reconciliation', addressed: true, origin: 'ai', reason: 'A bank reconciliation is in the folder.', basis: 'standard' },
      { id: 'D2', text: 'Confirm accruals are complete', addressed: false, origin: 'person', reason: '', basis: '' },
    ]
    mocks.data = panel(r)
    render(<PrecheckPanel jobKey="ACME-1" />)
    const list = screen.getByRole('heading', { name: 'Direction Note (1 of 2 drafted by AI)' }).parentElement!
    const rows = within(list).getAllByRole('listitem')
    expect(within(rows[0]).getByLabelText('Addressed')).toBeInTheDocument()
    expect(within(rows[0]).getByText('AI-drafted')).toBeInTheDocument()
    expect(rows[0]).toHaveTextContent('A bank reconciliation is in the folder.')
    expect(within(rows[1]).getByLabelText('Not addressed')).toBeInTheDocument()
    expect(within(rows[1]).queryByText('AI-drafted')).not.toBeInTheDocument()
  })

  it('a pre-check run shows its request list instead of findings', async () => {
    mocks.data = panel(run({ readiness: 'Requests to send', verdict: 'ready_with_exceptions', precheck: output, findings: [], coverage: { addressed: 1, total: 3 } }))
    render(
      <TooltipProvider>
        <PrecheckPanel jobKey="ACME-1" />
      </TooltipProvider>,
    )
    expect(screen.getByText('Requests to send', { selector: 'div' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '1 of 3 needed items received' })).toBeInTheDocument()
    expect(screen.getByLabelText('Items')).toHaveTextContent('2 to request')
    expect(screen.getByRole('heading', { name: 'Requests to send (2)' })).toBeInTheDocument()
    expect(screen.queryByText('Nothing found that needs attention.')).not.toBeInTheDocument()
  })

  it('complete with nothing found', () => {
    mocks.data = panel(run({ verdict: 'ready', counts: { high: 0, medium: 0, low: 0 }, coverage: { addressed: 2, total: 2 }, findings: [finding({ id: 3, status: 'addressed', severity: 'low' })] }))
    render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText('Ready for review')).toBeInTheDocument()
    expect(screen.getByText('Nothing found that needs attention.')).toBeInTheDocument()
    expect(screen.getByText(/A human review is still needed/)).toBeInTheDocument()
  })

  it('partial: says the budget was reached and what was skipped', () => {
    mocks.data = panel(run({ status: 'partial', skipped: [{ task_id: 'T3', direction_ref: 'D2', what: 'Confirm accruals are complete', reason: 'reader call limit reached' }] }))
    render(<PrecheckPanel jobKey="ACME-1" />)
    const notice = screen.getByText(/Not everything was done in this run/).closest('div')!
    expect(notice).toHaveTextContent('Confirm accruals are complete')
    expect(notice).toHaveTextContent('reader call limit reached')
  })

  it('failed: a plain reason and a retry', async () => {
    mocks.data = panel(run({ status: 'failed', verdict: '', findings: [], trail: {}, failure_reason: 'The pre-check cannot open this Drive folder. Share it (Viewer) with precheck@afit.iam.gserviceaccount.com.' }))
    render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByRole('alert')).toHaveTextContent('The pre-check did not finish')
    expect(screen.getByRole('alert')).toHaveTextContent('Share it (Viewer)')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(mocks.start).toHaveBeenCalled()
  })

  it('demo runs are labelled', () => {
    mocks.data = panel(run({ demo: true }))
    render(<PrecheckPanel jobKey="ACME-1" />)
    expect(screen.getByText('Demo mode: scripted answers, not Claude')).toBeInTheDocument()
  })
})

describe('helpers', () => {
  it('trail step state comes from events while running and from the trail when finished', () => {
    const live = run({ status: 'running', trail: {}, progress: [{ stage: 'read', state: 'running', label: 'Opening the job', counts: null }] })
    expect(trailStep(live, 'read')).toEqual({ state: 'running', label: 'Opening the job' })
    expect(trailStep(live, 'judged').state).toBe('waiting')
    expect(trailStep(run(), 'judged')).toEqual({ state: 'done', label: '5 findings weighed, 3 kept' })
  })

  it('cost chip', () => {
    expect(costChip(run({ usage: { totals: { input: 0, output: 0, cache_read: 0, cache_write: 0 }, cost_usd: 0, cache_share: 0 } }))).toBe('0 tokens · 0% from cache · $0.0000')
    expect(costChip(run({ usage: {} }))).toBeNull()
  })
})
