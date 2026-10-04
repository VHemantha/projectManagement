import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import styles from './CreateProjectDialog.module.css'
import { TaskNamesEditor } from './TaskNamesEditor'
import { useClients } from '@/api/clients'
import { extractErrorMessage } from '@/api/errors'
import { useCreateProject } from '@/api/projects'
import { useTeams } from '@/api/teams'
import type { ProjectType } from '@/api/types'
import { useUsers } from '@/api/users'
import { Button, Dialog, DialogContent, Input } from '@/design-system'
import { FEATURES } from '@/lib/features'
import { suggestKey } from '@/lib/projectKey'

interface CreateProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Where the new project starts: a sub-workspace (its workspace follows) or a workspace. */
  defaultClientId?: number
  defaultTeamId?: number
}

/** A project sits in a sub-workspace, which sits in a workspace:
 * Workspace > Sub-workspace > Project > Task. */
export function CreateProjectDialog({ open, onOpenChange, defaultClientId, defaultTeamId }: CreateProjectDialogProps) {
  const [name, setName] = useState('')
  const [key, setKey] = useState('')
  const [keyTouched, setKeyTouched] = useState(false)
  const [projectType, setProjectType] = useState<ProjectType>('kanban')
  const [leadId, setLeadId] = useState<string>('')
  const [taskNames, setTaskNames] = useState<string[]>([])
  // null: not touched yet, so the defaults (from where the dialog was opened) apply.
  const [teamChoice, setTeamChoice] = useState<string | null>(null)
  const [clientChoice, setClientChoice] = useState<string | null>(null)
  const { data: users } = useUsers()
  const { data: teams } = useTeams()
  const { data: clients } = useClients()
  const defaultClient = clients?.find((c) => c.id === defaultClientId)
  const clientId = clientChoice ?? (defaultClientId ? String(defaultClientId) : '')
  const teamId = teamChoice ?? String(defaultTeamId ?? defaultClient?.team_id ?? '')
  // Sub-workspaces of the chosen workspace (all of them when no workspace is chosen).
  const clientOptions = (clients ?? []).filter((c) => !teamId || String(c.team_id ?? '') === teamId)
  const createProject = useCreateProject()
  const navigate = useNavigate()

  const handleNameChange = (value: string) => {
    setName(value)
    if (!keyTouched) setKey(suggestKey(value))
  }

  const reset = () => {
    setName('')
    setKey('')
    setKeyTouched(false)
    setProjectType('kanban')
    setLeadId('')
    setTaskNames([])
    setTeamChoice(null)
    setClientChoice(null)
    createProject.reset()
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    createProject.mutate(
      {
        name,
        key,
        // Without the Scrum feature every new project is Kanban.
        project_type: FEATURES.scrum ? projectType : 'kanban',
        lead_id: leadId ? Number(leadId) : undefined,
        task_names: taskNames,
        client_id: clientId ? Number(clientId) : null,
        primary_team_id: teamId ? Number(teamId) : null,
      },
      {
        onSuccess: (project) => {
          onOpenChange(false)
          reset()
          navigate(`/projects/${project.key}`)
        },
      },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) reset()
      }}
    >
      <DialogContent title="Create project" maxWidth={520}>
        <form className={styles.form} onSubmit={handleSubmit}>
          {createProject.isError && (
            <div className={styles.formError}>{extractErrorMessage(createProject.error)}</div>
          )}

          {FEATURES.scrum && (
            <div>
              <div className={styles.typeRow}>
                <div
                  className={`${styles.typeCard} ${projectType === 'scrum' ? styles.selected : ''}`}
                  onClick={() => setProjectType('scrum')}
                >
                  <div className={styles.typeCardTitle}>Scrum</div>
                  <div className={styles.typeCardDesc}>Backlog, sprints, and a sprint board.</div>
                </div>
                <div
                  className={`${styles.typeCard} ${projectType === 'kanban' ? styles.selected : ''}`}
                  onClick={() => setProjectType('kanban')}
                >
                  <div className={styles.typeCardTitle}>Kanban</div>
                  <div className={styles.typeCardDesc}>Continuous flow board, no sprints.</div>
                </div>
              </div>
            </div>
          )}

          <Input
            id="project-name"
            label="Name"
            required
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="e.g. Michael Group"
          />
          <div className={styles.placementRow}>
            <div>
              <label className="tf-label" htmlFor="project-team" style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                Workspace
              </label>
              <select
                id="project-team"
                className={styles.select}
                value={teamId}
                onChange={(e) => {
                  setTeamChoice(e.target.value)
                  // A sub-workspace from another workspace no longer fits.
                  const current = clients?.find((c) => String(c.id) === clientId)
                  if (current && e.target.value && String(current.team_id ?? '') !== e.target.value) setClientChoice('')
                }}
              >
                <option value="">No workspace</option>
                {teams?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="tf-label" htmlFor="project-client" style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                Sub-workspace
              </label>
              <select
                id="project-client"
                className={styles.select}
                value={clientId}
                onChange={(e) => {
                  setClientChoice(e.target.value)
                  // The project goes where its sub-workspace is.
                  const picked = clients?.find((c) => String(c.id) === e.target.value)
                  if (picked?.team_id) setTeamChoice(String(picked.team_id))
                }}
              >
                <option value="">None (internal)</option>
                {clientOptions.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <Input
            id="project-key"
            label="Key"
            required
            value={key}
            maxLength={100}
            onChange={(e) => {
              setKeyTouched(true)
              setKey(e.target.value.replace(/[^A-Za-z0-9]/g, ''))
            }}
          />
          {key && <div className={styles.keyHint}>Tasks will be numbered {key}-1, {key}-2, …</div>}

          <div>
            <label className="tf-label" htmlFor="project-lead" style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              Lead
            </label>
            <select
              id="project-lead"
              className={styles.select}
              value={leadId}
              onChange={(e) => setLeadId(e.target.value)}
            >
              <option value="">Me (default)</option>
              {users?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="project-tasks" style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              Task names
            </label>
            <TaskNamesEditor id="project-tasks" value={taskNames} onChange={setTaskNames} />
          </div>

          <div className={styles.actions}>
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={createProject.isPending}>
              {createProject.isPending ? 'Creating…' : 'Create project'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
