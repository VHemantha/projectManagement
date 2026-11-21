import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PoliciesPanel } from './PoliciesPanel'
import type { PolicyLibrary } from '@/api/precheck'

const mocks = vi.hoisted(() => ({
  save: vi.fn((_p: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  feedback: vi.fn((_p: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.()),
  remove: vi.fn(),
  library: null as unknown as PolicyLibrary,
}))

vi.mock('@/api/precheck', () => ({
  usePolicies: () => ({ data: mocks.library, isLoading: false, isError: false }),
  usePolicy: () => ({ data: undefined }),
  useSavePolicy: () => ({ mutate: mocks.save, isPending: false, isError: false }),
  useDeletePolicy: () => ({ mutate: mocks.remove, isPending: false }),
  usePolicyFeedback: () => ({ mutate: mocks.feedback, isPending: false, isError: false, data: undefined }),
}))

const LIBRARY: PolicyLibrary = {
  scopes: [
    { value: 'client', label: 'Client' },
    { value: 'group', label: 'Group' },
    { value: 'location', label: 'Location' },
    { value: 'all', label: 'Every task' },
  ],
  clients: [{ id: 5, name: 'RWCA' }],
  groups: ['Lummis group'],
  locations: ['Auckland'],
  precheck_types: [{ value: 'residential_rental', label: 'Residential rental' }],
  policies: [
    { id: 9, scope: 'group', scope_label: 'Group: Lummis group', client: null, group: 'Lummis group', location: '', precheck_type: '',
      precheck_type_label: 'Every type of check', title: 'One email', text: 'Ask the Lummis group for everything in one email.', active: true,
      version: 2, history: [], created_by: 'Rita', updated_by: 'Rita', updated_at: '2026-11-20T09:00:00Z', can_change: true },
  ],
}

describe('Pre-check policies (AFIT, 20 Nov 2026)', () => {
  it('lists the policies with who they are for, and writes a new one for a client', async () => {
    mocks.library = LIBRARY
    render(<PoliciesPanel />)
    const card = within(screen.getByRole('list', { name: 'Policies' })).getByRole('listitem')
    expect(card).toHaveTextContent('One email')
    expect(card).toHaveTextContent('Group: Lummis group')
    expect(card).toHaveTextContent('Version 2')

    await userEvent.click(screen.getByRole('button', { name: /New policy/ }))
    const form = screen.getByRole('form', { name: 'New policy' })
    expect(within(form).getByRole('button', { name: 'Save policy' })).toBeDisabled()
    await userEvent.selectOptions(within(form).getByLabelText('Client'), '5')
    await userEvent.type(within(form).getByLabelText('Title'), 'No council rates')
    await userEvent.type(within(form).getByLabelText('What the pre-check should do'), 'Do not ask RWCA clients for council rates.')
    await userEvent.click(within(form).getByRole('button', { name: 'Save policy' }))
    expect(mocks.save).toHaveBeenCalledWith(
      { scope: 'client', client_id: 5, group: '', location: '', precheck_type: '', title: 'No council rates',
        text: 'Do not ask RWCA clients for council rates.', id: undefined },
      expect.anything(),
    )
  })

  it('takes feedback on a policy for the AI to revise it', async () => {
    mocks.library = LIBRARY
    render(<PoliciesPanel />)
    await userEvent.click(screen.getByRole('button', { name: /Feedback/ }))
    await userEvent.type(screen.getByLabelText('What should change in this policy?'), 'Not for sold properties.')
    await userEvent.click(screen.getByRole('button', { name: /Revise the policy/ }))
    expect(mocks.feedback).toHaveBeenCalledWith({ id: 9, text: 'Not for sold properties.', task: undefined, context: undefined }, expect.anything())
  })
})
