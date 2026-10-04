import { Building2, FolderKanban, ListTodo, Plus, Settings } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './TeamSubWorkspacesTab.module.css'
import { type ClientItem, useClients } from '@/api/clients'
import { useProjects } from '@/api/projects'
import type { TeamDetail } from '@/api/types'
import { Button } from '@/design-system'
import { CreateClientDialog } from '@/features/projects/CreateClientDialog'
import { CreateProjectDialog } from '@/features/projects/CreateProjectDialog'

/** A workspace's sub-workspaces, each with its projects: the next two levels of
 * Workspace > Sub-workspace > Project > Task, with a way to add to each. */
export function TeamSubWorkspacesTab({ team }: { team: TeamDetail }) {
  const { data: clients, isLoading } = useClients()
  const { data: projects } = useProjects()
  const [newSubWorkspace, setNewSubWorkspace] = useState(false)
  const [editing, setEditing] = useState<ClientItem | undefined>()
  const [newProjectIn, setNewProjectIn] = useState<number | null>(null)

  const mine = (clients ?? []).filter((c) => c.team_id === team.id)
  const projectsOf = (clientId: number) =>
    (projects ?? [])
      .filter((p) => p.client?.id === clientId && !p.is_archived)
      .sort((a, b) => Number(a.is_client_workspace) - Number(b.is_client_workspace) || a.name.localeCompare(b.name))

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <p className={styles.hint}>
          Sub-workspaces in {team.name}, and the projects in each. A task belongs to a project.
        </p>
        <Button variant="primary" size="sm" onClick={() => setNewSubWorkspace(true)}>
          <Plus size={14} /> New sub-workspace
        </Button>
      </div>

      {isLoading ? null : mine.length === 0 ? (
        <div className={styles.empty}>No sub-workspaces in {team.name} yet.</div>
      ) : (
        <ul className={styles.list}>
          {mine.map((client) => {
            const own = projectsOf(client.id)
            return (
              <li key={client.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <Building2 size={16} aria-hidden="true" className={styles.icon} />
                  <Link to={`/projects/all-issues?client=${client.id}`} className={styles.cardTitle}>
                    {client.name}
                  </Link>
                  {client.requires_projects && <span className={styles.badge}>Requires projects</span>}
                  <span className={styles.cardActions}>
                    <Button variant="subtle" size="sm" onClick={() => setNewProjectIn(client.id)}>
                      <Plus size={13} /> Project
                    </Button>
                    <Button variant="subtle" size="sm" aria-label={`${client.name} settings`} onClick={() => setEditing(client)}>
                      <Settings size={13} />
                    </Button>
                  </span>
                </div>
                {own.length === 0 ? (
                  <div className={styles.noProjects}>No projects yet.</div>
                ) : (
                  <ul className={styles.projects}>
                    {own.map((p) => (
                      <li key={p.key}>
                        <Link to={`/projects/${p.key}`} className={styles.project}>
                          {p.is_client_workspace ? <ListTodo size={14} aria-hidden="true" /> : <FolderKanban size={14} aria-hidden="true" />}
                          {p.is_client_workspace ? 'Tasks without a project' : p.name}
                          <span className={styles.count}>
                            {p.issue_count} task{p.issue_count === 1 ? '' : 's'}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <CreateClientDialog open={newSubWorkspace} onOpenChange={setNewSubWorkspace} defaultTeamId={team.id} />
      <CreateClientDialog open={!!editing} onOpenChange={(open) => !open && setEditing(undefined)} client={editing} />
      <CreateProjectDialog
        open={newProjectIn !== null}
        onOpenChange={(open) => !open && setNewProjectIn(null)}
        defaultClientId={newProjectIn ?? undefined}
        defaultTeamId={team.id}
      />
    </div>
  )
}
