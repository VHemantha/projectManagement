import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AIAssistant } from './AIAssistant'

const mocks = vi.hoisted(() => ({
  precheck: undefined as unknown,
  review: undefined as unknown,
  conversation: undefined as unknown,
}))

vi.mock('./PrecheckPanel', () => ({ PrecheckPanel: () => <p>pre-check panel</p> }))
vi.mock('./ReviewPanel', () => ({ ReviewPanel: () => <p>review panel</p> }))
vi.mock('./AskPanel', () => ({ AskPanel: () => <p>ask panel</p> }))
vi.mock('@/api/precheck', () => ({ useJobPrecheck: () => ({ data: mocks.precheck }) }))
vi.mock('@/api/review', () => ({ useJobReview: () => ({ data: mocks.review }) }))
vi.mock('@/api/ask', () => ({ useConversation: () => ({ data: mocks.conversation }) }))

describe('AIAssistant', () => {
  beforeEach(() => {
    mocks.precheck = { setup: { ready: true }, latest: { status: 'complete', readiness: 'Requests to send' } }
    mocks.review = { session: { status: 'in_progress' }, latest: { status: 'complete' }, rounds_done: 1,
                     findings: [{ status: 'open', severity: 'high' }, { status: 'open', severity: 'low' }, { status: 'closed', severity: 'high' }] }
    mocks.conversation = { questions: [{ status: 'answered' }, { status: 'answered' }] }
  })

  it('shows three buttons with where each stands, and opens each tool in its own window', async () => {
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
    render(<AIAssistant jobKey="SMITH-1" />)
    expect(screen.getByRole('button', { name: /Pre-check/ })).toHaveTextContent('Set up the Drive folder')
    expect(screen.getByRole('button', { name: /Review/ })).toHaveTextContent('Not run yet')
    expect(screen.getByRole('button', { name: /Ask/ })).toHaveTextContent('Ask anything about this task')
  })
})
