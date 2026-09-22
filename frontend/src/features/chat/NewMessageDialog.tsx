import { useState } from 'react'

import { useCreateDm } from '@/api/chat'
import type { Channel, User } from '@/api/types'
import { useUsers } from '@/api/users'
import { Avatar, Button, Dialog, DialogContent } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

interface NewMessageDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (channel: Channel) => void
}

export function NewMessageDialog({ open, onOpenChange, onCreated }: NewMessageDialogProps) {
  const currentUser = useAuthStore((s) => s.user)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<User[]>([])
  const { data: results } = useUsers(search.length >= 2 ? search : undefined)
  const createDm = useCreateDm()

  const toggle = (user: User) => {
    setSelected((prev) => (prev.some((u) => u.id === user.id) ? prev.filter((u) => u.id !== user.id) : [...prev, user]))
  }

  const reset = () => {
    setSearch('')
    setSelected([])
  }

  const handleStart = () => {
    if (selected.length === 0) return
    // The DM channel is find-or-created eagerly (it's a cheap, idempotent lookup), but it
    // won't show up in anyone's sidebar until has_messages flips true — see ChannelList's
    // filtering and ChannelSerializer.get_has_messages — so opening this dialog and closing it
    // without sending anything leaves nothing behind.
    createDm.mutate(
      selected.map((u) => u.id),
      {
        onSuccess: (channel) => {
          onOpenChange(false)
          reset()
          onCreated(channel)
        },
      },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) reset()
      }}
    >
      <DialogContent title="New message" maxWidth={420}>
        {selected.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
            {selected.map((u) => (
              <span
                key={u.id}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 12,
                  background: 'var(--tf-blue-subtle)',
                  color: 'var(--tf-blue)',
                  borderRadius: 999,
                  padding: '2px 8px',
                  cursor: 'pointer',
                }}
                onClick={() => toggle(u)}
              >
                {u.display_name} ×
              </span>
            ))}
          </div>
        )}
        <input
          autoFocus
          placeholder="Search people by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%',
            height: 36,
            borderRadius: 4,
            border: '2px solid var(--tf-border)',
            padding: '0 10px',
            marginBottom: 12,
          }}
        />
        <div style={{ maxHeight: 260, overflowY: 'auto' }}>
          {results
            ?.filter((u) => u.id !== currentUser?.id)
            .map((user) => (
              <div
                key={user.id}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 4px', cursor: 'pointer', fontSize: 13 }}
                onClick={() => toggle(user)}
              >
                <input type="checkbox" checked={selected.some((u) => u.id === user.id)} readOnly />
                <Avatar name={user.display_name} src={user.avatar} size={24} />
                <span>{user.display_name}</span>
              </div>
            ))}
          {search.length >= 2 && results?.length === 0 && (
            <div style={{ fontSize: 13, color: 'var(--tf-text-subtle)', padding: '8px 4px' }}>No matches.</div>
          )}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
          <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" variant="primary" disabled={selected.length === 0 || createDm.isPending} onClick={handleStart}>
            Start conversation
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
