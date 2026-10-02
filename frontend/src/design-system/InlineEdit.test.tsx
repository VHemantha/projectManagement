import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError, type AxiosResponse } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { InlineEdit } from './InlineEdit'

function apiError(data: unknown) {
  return new AxiosError('Bad request', '400', undefined, undefined, { data, status: 400 } as AxiosResponse)
}

describe('InlineEdit', () => {
  it('renames on click: Enter saves the tidied name and shows it straight away', async () => {
    let resolve!: () => void
    const onSave = vi.fn(() => new Promise<void>((r) => (resolve = r)))
    render(<InlineEdit value="Accounts" label="Team name" onSave={onSave} />)
    await userEvent.click(screen.getByText('Accounts'))
    const input = screen.getByRole('textbox', { name: 'Team name' })
    await userEvent.clear(input)
    await userEvent.type(input, '  Accounts   payable {Enter}')
    expect(onSave).toHaveBeenCalledWith('Accounts payable')
    // Optimistic: the new name shows before the save finishes.
    expect(screen.getByText('Accounts payable')).toBeInTheDocument()
    await act(async () => resolve())
  })

  it('Esc cancels without saving', async () => {
    const onSave = vi.fn(() => Promise.resolve())
    render(<InlineEdit value="Accounts" label="Team name" onSave={onSave} />)
    await userEvent.click(screen.getByRole('button', { name: 'Rename team name' }))
    await userEvent.type(screen.getByRole('textbox'), 'xyz{Escape}')
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText('Accounts')).toBeInTheDocument()
  })

  it('refuses an empty name', async () => {
    const onSave = vi.fn(() => Promise.resolve())
    render(<InlineEdit value="Accounts" label="Team name" onSave={onSave} />)
    await userEvent.click(screen.getByText('Accounts'))
    await userEvent.clear(screen.getByRole('textbox'))
    await userEvent.keyboard('{Enter}')
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent("Team name can't be empty.")
  })

  it('rolls back and shows the server error when saving fails', async () => {
    const onSave = vi.fn(() => Promise.reject(apiError({ name: ["There's already a team called 'Payroll'."] })))
    render(<InlineEdit value="Accounts" label="Team name" onSave={onSave} />)
    await userEvent.click(screen.getByText('Accounts'))
    await userEvent.clear(screen.getByRole('textbox'))
    await userEvent.type(screen.getByRole('textbox'), 'Payroll{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent("There's already a team called 'Payroll'.")
    expect(screen.getByText('Accounts')).toBeInTheDocument()
  })

  it('saves when leaving the box, and keeps the new name once the saved value arrives', async () => {
    const onSave = vi.fn(() => Promise.resolve())
    const { rerender } = render(<InlineEdit value="Draft" label="Filter name" onSave={onSave} />)
    await userEvent.click(screen.getByText('Draft'))
    await userEvent.clear(screen.getByRole('textbox'))
    await userEvent.type(screen.getByRole('textbox'), 'Final')
    await userEvent.tab()
    expect(onSave).toHaveBeenCalledWith('Final')
    rerender(<InlineEdit value="Final" label="Filter name" onSave={onSave} />)
    expect(screen.getByText('Final')).toBeInTheDocument()
  })

  it('is plain text for people who cannot rename', async () => {
    render(<InlineEdit value="Accounts" label="Team name" canEdit={false} onSave={vi.fn()} />)
    await userEvent.click(screen.getByText('Accounts'))
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('can require a double-click', async () => {
    render(<InlineEdit value="To do" label="Column name" activation="doubleClick" onSave={vi.fn()} />)
    await userEvent.click(screen.getByText('To do'))
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await userEvent.dblClick(screen.getByText('To do'))
    expect(screen.getByRole('textbox', { name: 'Column name' })).toHaveValue('To do')
  })
})
