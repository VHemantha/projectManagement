import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import styles from './TeamsListPage.module.css'
import { useCreateTeam, useTeams } from '@/api/teams'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

function CreateTeamDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [name, setName] = useState('')
  const createTeam = useCreateTeam()
  const navigate = useNavigate()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Create team" maxWidth={420}>
        <form
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
          onSubmit={(e) => {
            e.preventDefault()
            createTeam.mutate(
              { name },
              {
                onSuccess: (team) => {
                  onOpenChange(false)
                  setName('')
                  navigate(`/teams/${team.id}`)
                },
              },
            )
          }}
        >
          <Input id="team-name" label="Team name" required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
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
        <h1 className={styles.title}>Teams</h1>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus size={16} /> Create team
        </Button>
      </div>
      {isLoading ? (
        <div>Loading…</div>
      ) : (
        <div className={styles.grid}>
          {teams?.map((team) => (
            <div key={team.id} className={styles.card} onClick={() => navigate(`/teams/${team.id}`)}>
              <span className={styles.avatar} style={{ background: team.avatar_color }}>
                {team.name.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <div className={styles.name}>{team.name}</div>
                <div className={styles.meta}>{team.member_count} members</div>
              </div>
            </div>
          ))}
        </div>
      )}
      <CreateTeamDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
