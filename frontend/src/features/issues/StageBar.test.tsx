import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StageBar } from './StageBar'
import { textToDoc } from '@/api/stages'

const mocks = vi.hoisted(() => ({ add: vi.fn(), draft: vi.fn(), comments: [] as unknown[] }))

vi.mock('@/api/stages', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/stages')>()),
  useTaskStages: () => ({
    isLoading: false,
    data: [
      { key: 'precheck', label: 'Pre-check', state: 'done', done_on: '2026-11-04', due_date: '2026-11-05', subtask: 'SMITH-2', comments: 2 },
      { key: 'preparation', label: 'Preparation', state: 'active', done_on: null, due_date: '2026-11-12', subtask: 'SMITH-3', comments: 0 },
      { key: 'internal_review', label: 'Internal review', state: 'upcoming', done_on: null, due_date: '2026-11-13', subtask: 'SMITH-4', comments: 0 },
      { key: 'client_review', label: 'Client review', state: 'upcoming', done_on: null, due_date: null, subtask: 'SMITH-5', comments: 0 },
      { key: 'dispatch', label: 'Dispatch', state: 'upcoming', done_on: null, due_date: null, subtask: null, comments: 0 },
    ],
  }),
  useStageComments: () => ({ isLoading: false, data: mocks.comments }),
  useAddStageComment: () => ({ mutate: mocks.add, isPending: false, isError: false }),
  useDraftStageNote: () => ({ mutate: mocks.draft, isPending: false, isError: false }),
}))

const doc = (text: string) => ({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] })
const ann = { id: 1, display_name: 'Ann', avatar: null }

describe('The milestone bar (AFIT, 12 Nov 2026)', () => {
  beforeEach(() => {
    mocks.add.mockReset()
    mocks.draft.mockReset()
    mocks.comments = [
      { id: 2, author: ann, body: doc('Checks done; all documents in.'), stage: 'precheck', created_at: '2026-11-05T01:00:00Z' },
      { id: 1, author: ann, body: doc('AI pre-check — posted automatically on 04 Nov 2026, 09:00'), stage: 'precheck', created_at: '2026-11-04T01:00:00Z' },
    ]
  })

  it('shows the five stages, each done, active or to come, with its date', () => {
    render(<StageBar issueKey="SMITH-1" />)
    const steps = within(screen.getByRole('region', { name: 'Milestones' })).getAllByRole('listitem')
    expect(steps.map((s) => s.getAttribute('data-state'))).toEqual(['done', 'active', 'upcoming', 'upcoming', 'upcoming'])
    expect(steps[0]).toHaveTextContent('Pre-checkDone 4 Nov')
    expect(steps[1]).toHaveTextContent('Active · due 12 Nov')
    expect(steps[2]).toHaveTextContent('Due 13 Nov')
    expect(steps[3]).toHaveTextContent('Not scheduled')
    expect(screen.queryByRole('region', { name: /history/ })).not.toBeInTheDocument()
  })

  it("clicking a stage shows its history, the AI's results marked, newest first", async () => {
    render(<StageBar issueKey="SMITH-1" />)
    await userEvent.click(screen.getByRole('button', { name: /^Pre-check: Done 4 Nov, 2 comments/ }))
    const history = screen.getByRole('region', { name: 'Pre-check history' })
    const items = within(history).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Checks done; all documents in.')
    expect(items[0]).not.toHaveTextContent('AI result')
    expect(items[1]).toHaveTextContent('AI result')
    // Clicking it again closes it.
    await userEvent.click(screen.getByRole('button', { name: /^Pre-check:/ }))
    expect(screen.queryByRole('region', { name: 'Pre-check history' })).not.toBeInTheDocument()
  })

  it("records a stage's completion with a note the AI drafts from its results", async () => {
    mocks.comments = []
    mocks.draft.mockImplementation((_stage: string, opts: { onSuccess: (n: unknown) => void }) =>
      opts.onSuccess({ stage: 'preparation', label: 'Preparation', text: 'Preparation complete.\n- GST reconciled.', ai: true, facts: [] }))
    mocks.add.mockImplementation((_body: unknown, opts: { onSuccess: () => void }) => opts.onSuccess())
    render(<StageBar issueKey="SMITH-1" />)
    await userEvent.click(screen.getByRole('button', { name: /^Preparation:/ }))
    expect(screen.getByText(/No comments on the preparation yet/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Draft with AI' }))
    expect(mocks.draft).toHaveBeenCalledWith('preparation', expect.anything())
    const box = screen.getByRole('textbox', { name: 'Comment on the preparation' })
    expect(box).toHaveValue('Preparation complete.\n- GST reconciled.')
    expect(screen.getByText(/Drafted by the AI from the preparation's latest results/)).toBeInTheDocument()
    await userEvent.type(box, '\nAll journals posted.')
    await userEvent.click(screen.getByRole('button', { name: 'Post comment' }))
    expect(mocks.add).toHaveBeenCalledWith(
      { stage: 'preparation', body: textToDoc('Preparation complete.\n- GST reconciled.\nAll journals posted.') },
      expect.anything(),
    )
    expect(box).toHaveValue('')
  })
})

describe('textToDoc', () => {
  it('makes paragraphs, and bullets of "- " lines', () => {
    expect(textToDoc('Done.\n- One\n- Two\nAfter')).toEqual({
      type: 'doc',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'Done.' }] },
        {
          type: 'bulletList',
          content: [
            { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'One' }] }] },
            { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Two' }] }] },
          ],
        },
        { type: 'paragraph', content: [{ type: 'text', text: 'After' }] },
      ],
    })
  })
})
