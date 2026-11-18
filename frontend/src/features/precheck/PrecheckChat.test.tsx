import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PrecheckChat } from './PrecheckChat'

const mocks = vi.hoisted(() => ({
  addNote: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  run: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
}))

vi.mock('@/api/precheck', () => ({
  useAddAgentNote: () => ({ mutate: mocks.addNote, isPending: false, isError: false }),
  useRunPrecheck: () => ({ mutate: mocks.run, isPending: false, isError: false }),
}))
vi.mock('./AskPanel', () => ({
  AskPanel: ({ suggestions }: { suggestions: string[] }) => <div>chat with suggestions: {suggestions.join(' | ')}</div>,
}))

describe('The Pre-Check Agent chat (AFIT, 16 Nov 2026)', () => {
  it('is a chat about this pre-check, and a correction is kept on record before the pre-check runs again', async () => {
    render(<PrecheckChat jobKey="SMITH-1" running={false} />)
    expect(screen.getByRole('region', { name: 'Pre-Check Agent chat' })).toHaveTextContent('How were the Job Snapshot figures worked out?')
    await userEvent.type(screen.getByLabelText(/Correct the pre-check and run it again/), 'The equipment was leased, not bought.')
    await userEvent.click(screen.getByRole('button', { name: 'Save and re-run' }))
    expect(mocks.addNote).toHaveBeenCalledWith({ text: 'The equipment was leased, not bought.', agents: ['precheck'] }, expect.anything())
    expect(mocks.run).toHaveBeenCalled()
    expect(screen.getByText(/Saved. The pre-check is running again/)).toBeInTheDocument()
  })
})
