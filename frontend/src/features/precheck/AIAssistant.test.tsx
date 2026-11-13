import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AIAssistant } from './AIAssistant'

const mocks = vi.hoisted(() => ({
  precheck: undefined as unknown,
  review: undefined as unknown,
  conversation: undefined as unknown,
  guide: undefined as unknown,
  wp: undefined as unknown,
  ask: vi.fn(),
}))

vi.mock('./PrecheckPanel', () => ({ PrecheckPanel: () => <p>pre-check panel</p> }))
vi.mock('./ReviewPanel', () => ({ ReviewPanel: () => <p>review panel</p> }))
vi.mock('./AskPanel', () => ({ AskPanel: () => <p>ask panel</p> }))
vi.mock('./GuidePanel', () => ({ GuidePanel: () => <p>guide panel</p> }))
vi.mock('./WpAgentPanel', () => ({ WpAgentPanel: () => <p>wp agent panel</p> }))
vi.mock('@/api/precheck', () => ({
  useJobPrecheck: () => ({ data: mocks.precheck }),
  // The special notes panel under the tools (13 Nov 2026).
  useAgentNotes: () => ({ data: { notes: [], max: 20 } }),
  useAddAgentNote: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useRemoveAgentNote: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))
vi.mock('@/api/review', () => ({ useJobReview: () => ({ data: mocks.review }) }))
vi.mock('@/api/ask', () => ({
  useConversation: () => ({ data: mocks.conversation }),
  useAsk: () => ({ mutate: mocks.ask, isPending: false, isError: false }),
}))
vi.mock('@/api/guide', () => ({ useJobGuide: () => ({ data: mocks.guide }) }))
vi.mock('@/api/wpAgent', () => ({ useWpAgent: () => ({ data: mocks.wp }) }))

const tile = (name: string) => screen.getByRole('group', { name })

describe('AI workspace (AFIT, 12 Nov 2026 design)', () => {
  beforeEach(() => {
    mocks.ask.mockReset()
    mocks.precheck = { setup: { ready: true }, latest: { status: 'complete', readiness: 'Requests to send' } }
    mocks.review = { session: { status: 'in_progress' }, latest: { status: 'complete' }, rounds_done: 1,
                     findings: [{ status: 'open', severity: 'high' }, { status: 'open', severity: 'low' }, { status: 'closed', severity: 'high' }] }
    mocks.conversation = { questions: [{ status: 'answered' }, { status: 'answered' }] }
    mocks.guide = { has_precheck: true, latest: { status: 'complete', guide: { steps: [{}, {}, {}] } } }
    mocks.wp = { latest: { status: 'complete', gst: { status: 'Reconciled subject to corrections' } }, history: [], defaults: {} }
  })

  it('shows the four tools in order, each with where it stands, opening in its own window', async () => {
    render(<AIAssistant jobKey="SMITH-1" />)
    const region = screen.getByRole('region', { name: 'AI assistant' })
    expect(within(region).getByRole('heading', { name: 'AI workspace' })).toBeInTheDocument()
    const names = within(region).getAllByRole('group').map((g) => g.getAttribute('aria-label'))
    expect(names).toEqual(['Pre-check', 'Preparation guide', 'Workpaper agent', 'Review', 'Agents the note is for', 'Suggested questions'])
    expect(tile('Pre-check')).toHaveTextContent('Requests to send')
    expect(tile('Preparation guide')).toHaveTextContent('3 steps')
    expect(tile('Workpaper agent')).toHaveTextContent('GST: Reconciled subject to corrections')
    expect(tile('Review')).toHaveTextContent('2 open findings (1 high)')

    await userEvent.click(within(tile('Workpaper agent')).getByRole('button', { name: /Open workpapers/ }))
    expect(within(screen.getByRole('dialog', { name: 'WP Agent — reconciliations' })).getByText('wp agent panel')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    await userEvent.click(within(tile('Preparation guide')).getByRole('button', { name: /Open guide/ }))
    expect(within(screen.getByRole('dialog', { name: 'Preparation guide' })).getByText('guide panel')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    await userEvent.click(within(tile('Review')).getByRole('button', { name: /Open review/ }))
    expect(within(screen.getByRole('dialog', { name: 'AI review of the draft financial statements' })).getByText('review panel')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    await userEvent.click(within(tile('Pre-check')).getByRole('button', { name: /Open pre-check/ }))
    expect(within(screen.getByRole('dialog')).getByText('pre-check panel')).toBeInTheDocument()
  })

  it('marks the next tool to use: the pre-check first, then the guide, then the review', () => {
    mocks.precheck = { setup: { ready: false }, latest: null }
    mocks.review = { session: { status: 'in_progress' }, latest: null, rounds_done: 0, findings: [] }
    mocks.guide = { has_precheck: false, latest: null }
    mocks.wp = { latest: null, history: [], defaults: {} }
    const { unmount } = render(<AIAssistant jobKey="SMITH-1" />)
    expect(tile('Pre-check')).toHaveTextContent('Next step')
    expect(within(tile('Pre-check')).getByRole('button', { name: /Start pre-check/ })).toBeInTheDocument()
    expect(tile('Pre-check')).toHaveTextContent('Set up the Drive folder')
    expect(tile('Preparation guide')).toHaveTextContent('Best after the pre-check')
    expect(within(tile('Preparation guide')).getByRole('button', { name: /Generate guide/ })).toBeInTheDocument()
    expect(tile('Workpaper agent')).toHaveTextContent('Reconciliation workpapers')
    expect(within(tile('Review')).getByRole('button', { name: /Start review/ })).toBeInTheDocument()
    expect(screen.getAllByText('Next step')).toHaveLength(1)
    unmount()

    mocks.precheck = { setup: { ready: true }, latest: { status: 'complete', readiness: 'Ready' } }
    render(<AIAssistant jobKey="SMITH-1" />)
    expect(tile('Preparation guide')).toHaveTextContent('Next step')
    expect(tile('Pre-check')).not.toHaveTextContent('Next step')
  })

  it('a guide in the eight sections shows its event alerts', () => {
    mocks.guide = { has_precheck: true, latest: { status: 'complete', guide: { format: 2, events: [{ status: 'confirmed' }, { status: 'suspected' }] } } }
    render(<AIAssistant jobKey="SMITH-1" />)
    expect(tile('Preparation guide')).toHaveTextContent('2 event alerts, 1 to confirm')
  })

  it('asks a question from the page and opens the answer in its own window', async () => {
    mocks.ask.mockImplementation((_q: string, opts: { onSuccess: () => void }) => opts.onSuccess())
    render(<AIAssistant jobKey="SMITH-1" />)
    expect(screen.getByRole('button', { name: '2 questions asked' })).toBeInTheDocument()
    const box = screen.getByRole('textbox', { name: 'Ask anything about this job' })
    // A suggested question fills the box, to send as it is or to add to.
    await userEvent.click(screen.getByRole('button', { name: 'What is missing?' }))
    expect(box).toHaveValue('What is missing?')
    await userEvent.type(box, ' From the bank')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(mocks.ask).toHaveBeenCalledWith('What is missing? From the bank', expect.anything())
    expect(within(screen.getByRole('dialog', { name: 'Ask the AI about this task' })).getByText('ask panel')).toBeInTheDocument()
  })
})
