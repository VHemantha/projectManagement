import { Search } from 'lucide-react'
import { useState } from 'react'

import styles from './PeopleStrip.module.css'
import { useCreateDm } from '@/api/chat'
import { extractErrorMessage } from '@/api/errors'
import type { Channel } from '@/api/types'
import { useUsers } from '@/api/users'
import { Avatar } from '@/design-system'
import { useAuthStore } from '@/store/authStore'
import { usePresenceStore } from '@/store/presenceStore'

/** Everyone in the organisation as badges across the top of chat (AFIT, 12 Nov 2026): click one to
 * open your direct messages with them. The person you're talking to is highlighted, unread messages
 * show on their badge, and people online have a green dot. */
export function PeopleStrip({ channels, selectedId, onOpen }: {
  channels: Channel[] | undefined
  selectedId: number | null
  onOpen: (channel: Channel) => void
}) {
  const me = useAuthStore((s) => s.user)
  const onlineIds = usePresenceStore((s) => s.onlineUserIds)
  const { data: users } = useUsers()
  const createDm = useCreateDm()
  const [filter, setFilter] = useState('')

  // Your one-to-one conversation with each person, if there is one.
  const dmWith = new Map<number, Channel>()
  for (const c of channels ?? []) {
    if (c.channel_type !== 'direct_message') continue
    const other = c.participants.find((p) => p.id !== me?.id)
    if (other && c.participants.length === 2) dmWith.set(other.id, c)
  }

  const q = filter.trim().toLowerCase()
  const people = (users ?? [])
    .filter((u) => u.id !== me?.id) // /users/ leaves out the coordination agent
    .filter((u) => !q || u.display_name.toLowerCase().includes(q) || (u.job_title ?? '').toLowerCase().includes(q))
    // Online first, then by name.
    .sort((a, b) => Number(onlineIds.has(b.id)) - Number(onlineIds.has(a.id)) || a.display_name.localeCompare(b.display_name))

  const open = (userId: number) => {
    const existing = dmWith.get(userId)
    if (existing) return onOpen(existing)
    createDm.mutate([userId], { onSuccess: onOpen })
  }

  return (
    <section className={styles.strip} aria-label="Message someone">
      <div className={styles.head}>
        <span className={styles.title}>Message someone</span>
        <label className={styles.filter}>
          <Search size={14} aria-hidden="true" />
          <input aria-label="Find a person" placeholder="Find a person" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </label>
      </div>
      <ul className={styles.people}>
        {people.map((u) => {
          const dm = dmWith.get(u.id)
          const unread = dm?.unread_count ?? 0
          const online = onlineIds.has(u.id)
          const first = u.display_name.split(/\s+/)[0]
          return (
            <li key={u.id}>
              <button
                type="button"
                className={styles.badge}
                aria-pressed={dm != null && dm.id === selectedId}
                aria-label={`Message ${u.display_name}${online ? ' (online)' : ''}${unread ? `, ${unread} unread` : ''}`}
                title={u.job_title ? `${u.display_name} · ${u.job_title}` : u.display_name}
                onClick={() => open(u.id)}
                disabled={createDm.isPending}
              >
                <span className={styles.avatar}>
                  <Avatar name={u.display_name} src={u.avatar} size={26} />
                  {online && <span className={styles.online} aria-hidden="true" />}
                </span>
                <span className={styles.name}>{first}</span>
                {unread > 0 && <span className={styles.unread}>{unread > 99 ? '99+' : unread}</span>}
              </button>
            </li>
          )
        })}
        {users && people.length === 0 && <li className={styles.none}>No one matches.</li>}
      </ul>
      {createDm.isError && <p className={styles.error}>{extractErrorMessage(createDm.error)}</p>}
    </section>
  )
}
