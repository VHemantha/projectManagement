import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ForgotPasswordPage, ResetPasswordPage } from './PasswordResetPages'

const mocks = vi.hoisted(() => ({ requestMutate: vi.fn(), confirmMutate: vi.fn() }))

vi.mock('@/api/auth', () => ({
  useRequestPasswordReset: () => ({ mutate: mocks.requestMutate, isError: false, isPending: false, isSuccess: false }),
  useConfirmPasswordReset: () => ({ mutate: mocks.confirmMutate, isError: false, isPending: false, isSuccess: false }),
}))

function renderAt(url: string) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.requestMutate.mockClear()
  mocks.confirmMutate.mockClear()
})

describe('Password reset', () => {
  it('asks for a link by email', async () => {
    renderAt('/forgot-password')
    await userEvent.type(screen.getByLabelText('Email'), 'sandani.t@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Email me a link' }))
    expect(mocks.requestMutate).toHaveBeenCalledWith({ email: 'sandani.t@example.com' })
  })

  it('sets the new password with the link, once both entries match', async () => {
    renderAt('/reset-password?uid=Ng&token=abc-123')
    await userEvent.type(screen.getByLabelText('New password'), 'a-new-strong-pw-7')
    await userEvent.type(screen.getByLabelText('New password again'), 'something-else')
    await userEvent.click(screen.getByRole('button', { name: 'Set password' }))
    expect(screen.getByRole('alert')).toHaveTextContent("don't match")
    expect(mocks.confirmMutate).not.toHaveBeenCalled()
    await userEvent.clear(screen.getByLabelText('New password again'))
    await userEvent.type(screen.getByLabelText('New password again'), 'a-new-strong-pw-7')
    await userEvent.click(screen.getByRole('button', { name: 'Set password' }))
    expect(mocks.confirmMutate).toHaveBeenCalledWith({ uid: 'Ng', token: 'abc-123', password: 'a-new-strong-pw-7' })
  })

  it('explains an incomplete link', () => {
    renderAt('/reset-password')
    expect(screen.getByRole('alert')).toHaveTextContent('incomplete')
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument()
  })
})
