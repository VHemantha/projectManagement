import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NotesConsidered, SpecialNotes } from './SpecialNotes'

const mocks = vi.hoisted(() => ({
  notes: [] as unknown[],
  add: vi.fn((_b: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  remove: vi.fn(),
}))

vi.mock('@/api/precheck', () => ({
  useAgentNotes: () => ({ data: { notes: mocks.notes, max: 20 } }),
  useAddAgentNote: () => ({ mutate: mocks.add, isPending: false, isError: false }),
  useRemoveAgentNote: () => ({ mutate: mocks.remove, isPending: false, isError: false }),
}))

const note = (id: number, text: string, agents: string[], can_edit: boolean) => ({ id, text, agents, by: 'Rita', by_id: 1, created_at: '', can_edit })

describe('Special notes for the AI (AFIT, 13 Nov 2026)', () => {
  beforeEach(() => {
    mocks.add.mockClear()
    mocks.remove.mockClear()
  })

  it('lists the notes with who they are for, and removes only those the person may change', async () => {
    mocks.notes = [note(1, 'Treat this year as the year of sale.', [], true), note(2, 'Check depreciation recovery.', ['review'], false)]
    render(<SpecialNotes jobKey="SMITH-1" />)
    expect(screen.getByText('Treat this year as the year of sale.')).toBeInTheDocument()
    expect(screen.getByText('For: all agents')).toBeInTheDocument()
    expect(screen.getByText('For: Review')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove note: Check depreciation recovery.' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove note: Treat this year as the year of sale.' }))
    expect(mocks.remove).toHaveBeenCalledWith(1)
  })

  it('adds a note for every agent, or for the agents ticked', async () => {
    mocks.notes = []
    render(<SpecialNotes jobKey="SMITH-1" />)
    const add = screen.getByRole('button', { name: 'Add note' })
    expect(add).toBeDisabled()
    expect(screen.getByText('None ticked: every agent.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('New note for the AI'), 'Keep the client email short.')
    await userEvent.click(screen.getByLabelText('Pre-check'))
    await userEvent.click(screen.getByLabelText('Ask'))
    await userEvent.click(add)
    expect(mocks.add).toHaveBeenCalledWith({ text: 'Keep the client email short.', agents: ['precheck', 'ask'] }, expect.anything())
    expect(screen.getByLabelText('New note for the AI')).toHaveValue('')
  })

  it('a result shows the notes it was given and which one it used', () => {
    render(<NotesConsidered notes={[{ id: 'SN1', text: 'Year of sale.', by: 'Rita', cited: true }, { id: 'SN2', text: 'Short email.', by: '', cited: false }]} />)
    const group = screen.getByRole('group', { name: 'Special notes considered' })
    expect(group).toHaveTextContent('Year of sale.')
    expect(group).toHaveTextContent('Short email.')
    expect(screen.getAllByText('Used in this result')).toHaveLength(1)
  })
})
