import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AIAssistant } from './AIAssistant'

const mocks = vi.hoisted(() => ({
  precheck: undefined as unknown,
  review: undefined as unknown,
  conversation: undefined as unknown,
  guide: undefined as unknown,
}))

vi.mock('./PrecheckPanel', () => ({ PrecheckPanel: () => <p>pre-check panel</p> }))
vi.mock('./ReviewPanel', () => ({ ReviewPanel: () => <p>review panel</p> }))
vi.mock('./AskPanel', () => ({ AskPanel: () => <p>ask panel</p> }))
vi.mock('./GuidePanel', () => ({ GuidePanel: () => <p>guide panel</p> }))
vi.mock('./Milestones', () => ({ Milestones: () => <p>milestones</p> }))
vi.mock('@/api/precheck', () => ({ useJobPrecheck: () => ({ data: mocks.precheck }) }))
vi.mock('@/api/review', () => ({ useJobReview: () => ({ data: mocks.review }) }))
vi.mock('@/api/ask', () => ({ useConversation: () => ({ data: mocks.conversation }) }))
vi.mock('@/api/guide', () => ({ useJobGuide: () => ({ data: mocks.guide }) }))

describe('AIAssistant', () => {
  beforeEach(() => {
    mocks.precheck = { setup: { ready: true }, latest: { status: 'complete', readiness: 'Requests to send' } }
    mocks.review = { session: { status: 'in_progress' }, latest: { status: 'complete' }, rounds_done: 1,
                     findings: [{ status: 'open', severity: 'high' }, { status: 'open', severity: 'low' }, { status: 'closed', severity: 'high' }] }
    mocks.conversation = { questions: [{ status: 'answered' }, { status: 'answered' }] }
    mocks.guide = { has_precheck: true, latest: { status: 'complete', guide: { steps: [{}, {}, {}] } } }
  })

  it('shows four buttons in order — Pre-check, Guide, Ask, Review — with where each stands', async () => {
    render(<AIAssistant jobKey="SMITH-1" />)
    const names = within(screen.getByRole('region', { name: 'AI assistant' })).getAllByRole('button').map((b) => b.textContent ?? '')
    expect(names.map((n) => n.match(/^(Pre-check|Guide|Ask|Review)/)?.[1])).toEqual(['Pre-check', 'Guide', 'Ask', 'Review'])
    expect(screen.getByRole('button', { name: /Guide/ })).toHaveTextContent('3 steps')
    expect(screen.getByText('milestones')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Guide/ }))
    expect(within(screen.getByRole('dialog', { name: 'Preparation guide' })).getByText('guide panel')).toBeInTheDocument()
  })

  it('opens each tool in its own window', async () => {
    render(<AIAssistant jobKey="SMITH-1" />)
    const precheck = screen.getByRole('button', { name: /Pre-check/ })
    expect(precheck).toHaveTextContent('Requests to send')
    expect(screen.getByRole('button', { name: /Review/ })).toHaveTextContent('2 open findings (1 high)')
    expect(screen.getByRole('button', { name: /Ask/ })).toHaveTextContent('2 questions asked')
    expect(screen.queryByText('pre-check panel')).not.toBeInTheDocument()

    await userEvent.click(precheck)
    expect(within(screen.getByRole('dialog')).getByText('pre-check panel')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Review/ }))
    expect(within(screen.getByRole('dialog', { name: 'AI review of the draft financial statements' })).getByText('review panel')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    await userEvent.click(screen.getByRole('button', { name: /Ask/ }))
    expect(within(screen.getByRole('dialog', { name: 'Ask the AI about this task' })).getByText('ask panel')).toBeInTheDocument()
  })

  it('before anything has run', () => {
    mocks.precheck = { setup: { ready: false }, latest: null }
    mocks.review = { session: { status: 'in_progress' }, latest: null, rounds_done: 0, findings: [] }
    mocks.conversation = { questions: [] }
    mocks.guide = { has_precheck: false, latest: null }
    render(<AIAssistant jobKey="SMITH-1" />)
    expect(screen.getByRole('button', { name: /Pre-check/ })).toHaveTextContent('Set up the Drive folder')
    expect(screen.getByRole('button', { name: /Review/ })).toHaveTextContent('Not run yet')
    expect(screen.getByRole('button', { name: /Ask/ })).toHaveTextContent('Ask anything about this task')
    expect(screen.getByRole('button', { name: /Guide/ })).toHaveTextContent('Best after the pre-check')
  })
})
