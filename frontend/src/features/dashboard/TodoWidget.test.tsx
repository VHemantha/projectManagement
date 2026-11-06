import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { TodoItem } from '@/api/todos'
import { TodoWidget } from './TodoWidget'

const mocks = vi.hoisted(() => ({ add: vi.fn(), update: vi.fn(), remove: vi.fn(), clear: vi.fn() }))

const ITEMS: TodoItem[] = [
  { id: 1, text: 'Call ABC Ltd about the rates notice', kind: 'work', due_date: '2020-01-01', done: false, done_at: null, created_at: '' },
  { id: 2, text: 'Book the dentist', kind: 'personal', due_date: null, done: false, done_at: null, created_at: '' },
  { id: 3, text: 'Renew the parking permit', kind: 'personal', due_date: null, done: true, done_at: '2026-11-04T09:00:00Z', created_at: '' },
]

vi.mock('@/api/todos', () => ({
  useTodos: () => ({ data: ITEMS, isLoading: false }),
  useAddTodo: () => ({ mutate: mocks.add, isPending: false, isError: false }),
  useUpdateTodo: () => ({ mutate: mocks.update }),
  useDeleteTodo: () => ({ mutate: mocks.remove }),
  useClearDoneTodos: () => ({ mutate: mocks.clear, isPending: false }),
}))

describe('To-do list (AFIT, 5 Nov 2026)', () => {
  it('lists open and done items, private to the person, work and personal', async () => {
    render(<TodoWidget />)
    const card = screen.getByRole('region', { name: 'To-do list' })
    expect(card).toHaveTextContent('Only you can see this list.')
    const open = within(card).getByRole('list', { name: 'To do' })
    expect(within(open).getAllByRole('listitem')).toHaveLength(2)
    expect(open).toHaveTextContent('Overdue · 01-01-20')
    expect(within(card).getByRole('list', { name: 'Done' })).toHaveTextContent('Renew the parking permit')

    await userEvent.click(within(card).getByRole('button', { name: 'Personal' }))
    expect(within(card).getByRole('list', { name: 'To do' })).not.toHaveTextContent('Call ABC Ltd')
  })

  it('adds, ticks, deletes and clears', async () => {
    render(<TodoWidget />)
    await userEvent.type(screen.getByRole('textbox', { name: 'New to-do' }), 'Pick up the kids at 3')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Work or personal' }), 'personal')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(mocks.add).toHaveBeenCalledWith({ text: 'Pick up the kids at 3', kind: 'personal', due_date: null }, expect.anything())

    await userEvent.click(screen.getByRole('checkbox', { name: 'Book the dentist' }))
    expect(mocks.update).toHaveBeenCalledWith({ id: 2, done: true })
    await userEvent.click(screen.getByRole('button', { name: 'Delete: Book the dentist' }))
    expect(mocks.remove).toHaveBeenCalledWith(2)
    await userEvent.click(screen.getByRole('button', { name: 'Clear done' }))
    expect(mocks.clear).toHaveBeenCalled()
  })
})
