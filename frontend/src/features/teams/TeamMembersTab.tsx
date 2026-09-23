import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import { useAddTeamMember, useRemoveTeamMember, useUpdateTeamMember } from '@/api/teams'
import type { TeamDetail } from '@/api/types'
import { useUsers } from '@/api/users'
import { Avatar, Button } from '@/design-system'

const selectStyle = {
  height: 32,
  borderRadius: 4,
  border: '1px solid var(--tf-border)',
  padding: '0 8px',
  fontSize: 13,
  background: 'var(--tf-surface)',
  color: 'var(--tf-text)',
}

export function TeamMembersTab({ team }: { team: TeamDetail }) {
  const { data: users } = useUsers()
  const addMember = useAddTeamMember(team.id)
  const updateMember = useUpdateTeamMember(team.id)
  const removeMember = useRemoveTeamMember(team.id)
  const [pickedUserId, setPickedUserId] = useState('')
  const [pickedRole, setPickedRole] = useState<'member' | 'lead'>('member')

  const existingIds = new Set(team.memberships.map((m) => m.user.id))
  const candidates = (users ?? []).filter((u) => !existingIds.has(u.id))

  return (
    <div style={{ padding: '0 24px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, marginBottom: 20 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Add member</label>
          <select
            style={{ ...selectStyle, width: '100%', height: 36 }}
            value={pickedUserId}
            onChange={(e) => setPickedUserId(e.target.value)}
          >
            <option value="">Select a person…</option>
            {candidates.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Role</label>
          <select
            style={{ ...selectStyle, height: 36 }}
            value={pickedRole}
            onChange={(e) => setPickedRole(e.target.value as 'member' | 'lead')}
          >
            <option value="member">Member</option>
            <option value="lead">Lead</option>
          </select>
        </div>
        <Button
          variant="secondary"
          disabled={!pickedUserId || addMember.isPending}
          onClick={() => {
            addMember.mutate({ user_id: Number(pickedUserId), role: pickedRole })
            setPickedUserId('')
            setPickedRole('member')
          }}
        >
          Add
        </Button>
      </div>

      {team.memberships.length === 0 ? (
        <div style={{ color: 'var(--tf-text-subtle)', fontSize: 13 }}>No members yet.</div>
      ) : (
        team.memberships.map((m) => (
          <div
            key={m.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 0',
              borderBottom: '1px solid var(--tf-border)',
            }}
          >
            <Avatar name={m.user.display_name} src={m.user.avatar} size={32} userId={m.user.id} interactive />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{m.user.display_name}</div>
              <div style={{ fontSize: 12, color: 'var(--tf-text-subtle)' }}>{m.user.email}</div>
            </div>
            <select
              style={selectStyle}
              value={m.role}
              onChange={(e) => updateMember.mutate({ membershipId: m.id, role: e.target.value })}
            >
              <option value="member">Member</option>
              <option value="lead">Lead</option>
            </select>
            <Button
              variant="subtle"
              iconOnly
              size="sm"
              onClick={() => removeMember.mutate(m.id)}
              aria-label="Remove member"
            >
              <Trash2 size={14} />
            </Button>
          </div>
        ))
      )}
    </div>
  )
}
