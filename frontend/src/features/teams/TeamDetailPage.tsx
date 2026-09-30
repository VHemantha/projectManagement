import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import styles from './TeamBoardPage.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useDeleteTeam, useTeam } from '@/api/teams'
import type { TeamDetail } from '@/api/types'
import { TeamBoard } from './TeamBoard'
import { TeamGoalsTab } from './TeamGoalsTab'
import { TeamIssuesTab } from './TeamIssuesTab'
import { TeamMembersTab } from './TeamMembersTab'
import { Button, Dialog, DialogContent, Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

function DeleteTeamDialog({
  team,
  open,
  onOpenChange,
}: {
  team: TeamDetail
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const navigate = useNavigate()
  const deleteTeam = useDeleteTeam()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={`Delete ${team.name}?`} maxWidth={440}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, fontSize: 14 }}>
          <p style={{ margin: 0 }}>This permanently deletes:</p>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>the team and its {team.memberships.length} membership(s)</li>
            <li>the team&apos;s chat channel and all of its messages</li>
          </ul>
          <p style={{ margin: 0, color: 'var(--tf-text-subtle)' }}>
            Members, projects and jobs are kept. Projects and sub-teams linked to this team are
            unlinked from it.
          </p>
          {deleteTeam.isError && (
            <div style={{ color: 'var(--tf-danger)' }}>{extractErrorMessage(deleteTeam.error)}</div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={deleteTeam.isPending}
              onClick={() => deleteTeam.mutate(team.id, { onSuccess: () => navigate('/teams') })}
            >
              {deleteTeam.isPending ? 'Deleting…' : 'Delete team'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function TeamDetailPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const { data: team } = useTeam(teamId)
  const currentUser = useAuthStore((s) => s.user)
  const [deleteOpen, setDeleteOpen] = useState(false)

  if (!team) return null

  // Mirrors the backend rule (TeamViewSet.perform_destroy): staff or one of the team's leads.
  const canDelete =
    !!currentUser &&
    (currentUser.is_staff || team.memberships.some((m) => m.user.id === currentUser.id && m.role === 'lead'))

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className={styles.header}>
        <span className={styles.avatar} style={{ background: team.avatar_color }}>
          {team.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <div className={styles.title}>{team.name}</div>
          <div className={styles.subtitle}>
            {team.memberships.length} members
            {team.parent && (
              <>
                {' · Part of '}
                <Link to={`/teams/${team.parent.id}`} style={{ color: 'var(--tf-blue)' }}>
                  {team.parent.name}
                </Link>
              </>
            )}
            {team.sub_teams.length > 0 && (
              <>
                {' · '}
                {team.sub_teams.length} sub-team{team.sub_teams.length > 1 ? 's' : ''}
              </>
            )}
          </div>
        </div>
        {canDelete && (
          <div style={{ marginLeft: 'auto' }}>
            <Button variant="subtle" onClick={() => setDeleteOpen(true)}>
              <Trash2 size={14} />
              Delete team
            </Button>
          </div>
        )}
      </div>
      {canDelete && <DeleteTeamDialog team={team} open={deleteOpen} onOpenChange={setDeleteOpen} />}

      <Tabs defaultValue="board" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ padding: '0 24px' }}>
          <TabsList>
            <TabsTrigger value="board">Board</TabsTrigger>
            <TabsTrigger value="issues">Jobs</TabsTrigger>
            <TabsTrigger value="goals">Team goals</TabsTrigger>
            <TabsTrigger value="members">Members</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="board" style={{ flex: 1, minHeight: 0 }}>
          <TeamBoard team={team} />
        </TabsContent>
        <TabsContent value="issues">
          <TeamIssuesTab team={team} />
        </TabsContent>
        <TabsContent value="goals">
          <TeamGoalsTab team={team} />
        </TabsContent>
        <TabsContent value="members">
          <TeamMembersTab team={team} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
