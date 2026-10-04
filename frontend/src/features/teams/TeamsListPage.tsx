import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import styles from './TeamsListPage.module.css'
import { useCreateTeam, useTeams } from '@/api/teams'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

function CreateTeamDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState('')
  const { data: teams } = useTeams()
  const createTeam = useCreateTeam()
  const navigate = useNavigate()

  // Only top-level workspaces (no parent of their own) can hold another — matches the org
  // chart's exact 2-level depth.
  const topLevelTeams = (teams ?? []).filter((t) => !t.parent)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Create workspace" maxWidth={420}>
        <form
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
          onSubmit={(e) => {
            e.preventDefault()
            createTeam.mutate(
              { name, parent_id: parentId ? Number(parentId) : undefined },
              {
                onSuccess: (team) => {
                  onOpenChange(false)
                  setName('')
                  setParentId('')
                  navigate(`/workspaces/${team.id}`)
                },
              },
            )
          }}
        >
          <Input id="team-name" label="Workspace name" required autoFocus placeholder="e.g. Team 1" value={name} onChange={(e) => setName(e.target.value)} />
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              Part of (optional)
            </label>
            <select
              style={{
                width: '100%', height: 36, borderRadius: 4, border: '1px solid var(--tf-border)',
                padding: '0 10px', fontSize: 13, background: 'var(--tf-surface)', color: 'var(--tf-text)',
              }}
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
            >
              <option value="">None (top level)</option>
              {topLevelTeams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!name.trim() || createTeam.isPending}>
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function TeamsListPage() {
  const { data: teams, isLoading } = useTeams()
  const [createOpen, setCreateOpen] = useState(false)
  const navigate = useNavigate()

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Workspaces</h1>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus size={16} /> Create workspace
        </Button>
      </div>
      {isLoading ? (
        <div>Loading…</div>
      ) : (
        <div className={styles.grid}>
          {teams?.map((team) => (
            <div key={team.id} className={styles.card} onClick={() => navigate(`/workspaces/${team.id}`)}>
              <span className={styles.avatar} style={{ background: team.avatar_color }}>
                {team.name.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <div className={styles.name}>{team.name}</div>
                <div className={styles.meta}>
                  {team.member_count} members{team.parent && ` · ${team.parent.name}`}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <CreateTeamDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
