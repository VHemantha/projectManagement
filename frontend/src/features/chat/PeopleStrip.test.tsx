import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PeopleStrip } from './PeopleStrip'
import type { Channel } from '@/api/types'
import { useAuthStore } from '@/store/authStore'
import { usePresenceStore } from '@/store/presenceStore'

const mocks = vi.hoisted(() => ({ createDm: vi.fn() }))
const person = (id: number, display_name: string, job_title = '') => ({ id, display_name, job_title, avatar: null, email: `${id}@x.nz` })
vi.mock('@/api/users', () => ({
  useUsers: () => ({ data: [person(1, 'Me Myself'), person(2, 'Ann Lee', 'Accountant'), person(3, 'Bob Kaur'), person(4, 'Cara Ng')] }),
}))
vi.mock('@/api/chat', () => ({ useCreateDm: () => ({ mutate: mocks.createDm, isPending: false, isError: false }) }))
vi.mock('@/design-system', () => ({ Avatar: ({ name }: { name: string }) => <span>{name[0]}</span> }))

const dmWithBob = {
  id: 9, channel_type: 'direct_message', unread_count: 3, participants: [person(1, 'Me Myself'), person(3, 'Bob Kaur')],
} as unknown as Channel

describe('Everyone as badges at the top of chat (AFIT, 12 Nov 2026)', () => {
  beforeEach(() => {
    mocks.createDm.mockReset()
    useAuthStore.setState({ user: { id: 1, email: '1@x.nz', username: 'me', display_name: 'Me Myself', job_title: '', avatar: null, is_staff: false } })
    usePresenceStore.getState().setSnapshot([4])
  })

  it('shows everyone but you, online first, with unread messages on their badge', () => {
    render(<PeopleStrip channels={[dmWithBob]} selectedId={null} onOpen={vi.fn()} />)
    const badges = within(screen.getByRole('region', { name: 'Message someone' })).getAllByRole('button')
    expect(badges.map((b) => b.getAttribute('aria-label'))).toEqual(['Message Cara Ng (online)', 'Message Ann Lee', 'Message Bob Kaur, 3 unread'])
  })

  it('opens your conversation with someone, or starts one', async () => {
    const onOpen = vi.fn()
    render(<PeopleStrip channels={[dmWithBob]} selectedId={9} onOpen={onOpen} />)
    expect(screen.getByRole('button', { name: /Message Bob Kaur/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /Message Bob Kaur/ }))
    expect(onOpen).toHaveBeenCalledWith(dmWithBob)
    expect(mocks.createDm).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Message Ann Lee' }))
    expect(mocks.createDm).toHaveBeenCalledWith([2], { onSuccess: onOpen })
  })

  it('finds a person by name or job title', async () => {
    render(<PeopleStrip channels={[]} selectedId={null} onOpen={vi.fn()} />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Find a person' }), 'account')
    expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual(['Message Ann Lee'])
  })
})
