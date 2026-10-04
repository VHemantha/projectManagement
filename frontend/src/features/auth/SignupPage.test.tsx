import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SignupPage } from './SignupPage'
import { TooltipProvider } from '@/design-system'
import { InviteButton } from '@/features/people/Invitations'

const mocks = vi.hoisted(() => ({
  preview: { data: undefined as unknown, isError: false, isLoading: false, error: null as unknown },
  signupMutate: vi.fn(),
  createMutate: vi.fn(),
  created: null as unknown,
}))

vi.mock('@/api/invitations', () => ({
  useInvitationPreview: () => mocks.preview,
  useCreateInvitation: () => ({ mutate: mocks.createMutate, data: mocks.created, isError: false, isPending: false, reset: vi.fn() }),
}))
vi.mock('@/api/auth', () => ({ useSignup: () => ({ mutate: mocks.signupMutate, isError: false, isPending: false }) }))
vi.mock('@/api/teams', () => ({ useTeams: () => ({ data: [{ id: 4, name: 'Payroll' }] }) }))

function renderAt(url: string) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/signup" element={<SignupPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.preview = { data: undefined, isError: false, isLoading: false, error: null }
  mocks.signupMutate.mockClear()
  mocks.createMutate.mockClear()
  mocks.created = null
})

describe('SignupPage', () => {
  it('is closed without an invitation', () => {
    renderAt('/signup')
    expect(screen.getByRole('alert')).toHaveTextContent('Sign-up is by invitation only')
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })

  it('explains a dead link', () => {
    mocks.preview = { data: undefined, isError: true, isLoading: false, error: new Error('gone') }
    renderAt('/signup?invite=old')
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })

  it('signs up with the invited email locked', async () => {
    mocks.preview = {
      data: { email: 'new@example.com', role: 'worker', team_name: 'Payroll', invited_by_name: 'Boss', expires_at: '' },
      isError: false,
      isLoading: false,
      error: null,
    }
    renderAt('/signup?invite=tok123')
    expect(screen.getByText(/Boss invited you to join as a worker in the Payroll workspace/)).toBeInTheDocument()
    const email = screen.getByLabelText('Email')
    expect(email).toHaveValue('new@example.com')
    expect(email).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Full name'), 'New Person')
    await userEvent.type(screen.getByLabelText('Username'), 'newbie')
    await userEvent.type(screen.getByLabelText('Password'), 'a-strong-pw-1')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(mocks.signupMutate).toHaveBeenCalledWith(
      { invite_token: 'tok123', username: 'newbie', password: 'a-strong-pw-1', display_name: 'New Person' },
      expect.anything(),
    )
  })
})

describe('Inviting people', () => {
  it('sends an invitation with role and workspace', async () => {
    render(
      <TooltipProvider>
        <InviteButton />
      </TooltipProvider>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Invite people' }))
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
    await userEvent.selectOptions(screen.getByLabelText('Role'), 'admin')
    await userEvent.selectOptions(screen.getByLabelText('Workspace (optional)'), '4')
    await userEvent.click(screen.getByRole('button', { name: 'Send invitation' }))
    expect(mocks.createMutate).toHaveBeenCalledWith({ email: 'new@example.com', role: 'admin', team_id: 4 })
  })

  it('shows the link to copy when the email could not be sent', async () => {
    mocks.created = { email: 'new@example.com', invite_url: 'https://app/signup?invite=abc', email_sent: false }
    render(
      <TooltipProvider>
        <InviteButton />
      </TooltipProvider>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Invite people' }))
    expect(screen.getByRole('status')).toHaveTextContent("couldn't be sent")
    expect(screen.getByText('https://app/signup?invite=abc')).toBeInTheDocument()
  })
})
