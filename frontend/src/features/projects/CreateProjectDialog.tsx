import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import styles from './CreateProjectDialog.module.css'
import { TaskNamesEditor } from './TaskNamesEditor'
import { extractErrorMessage } from '@/api/errors'
import { useCreateProject } from '@/api/projects'
import type { ProjectType } from '@/api/types'
import { useUsers } from '@/api/users'
import { Button, Dialog, DialogContent, Input } from '@/design-system'
import { suggestKey } from '@/lib/projectKey'

interface CreateProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateProjectDialog({ open, onOpenChange }: CreateProjectDialogProps) {
  const [name, setName] = useState('')
  const [key, setKey] = useState('')
  const [keyTouched, setKeyTouched] = useState(false)
  const [projectType, setProjectType] = useState<ProjectType>('scrum')
  const [leadId, setLeadId] = useState<string>('')
  const [taskNames, setTaskNames] = useState<string[]>([])
  const { data: users } = useUsers()
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
    setProjectType('scrum')
    setLeadId('')
    setTaskNames([])
    createProject.reset()
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    createProject.mutate(
      {
        name,
        key,
        project_type: projectType,
        lead_id: leadId ? Number(leadId) : undefined,
        task_names: taskNames,
      },
      {
        onSuccess: (project) => {
          onOpenChange(false)
          reset()
          navigate(`/workspaces/${project.key}`)
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
      <DialogContent title="Create workspace" maxWidth={520}>
        <form className={styles.form} onSubmit={handleSubmit}>
          {createProject.isError && (
            <div className={styles.formError}>{extractErrorMessage(createProject.error)}</div>
          )}

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

          <Input
            id="project-name"
            label="Name"
            required
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="e.g. Mobile App Revamp"
          />
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
          {key && <div className={styles.keyHint}>Jobs will be numbered {key}-1, {key}-2, …</div>}

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
              Tasks
            </label>
            <TaskNamesEditor id="project-tasks" value={taskNames} onChange={setTaskNames} />
          </div>

          <div className={styles.actions}>
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={createProject.isPending}>
              {createProject.isPending ? 'Creating…' : 'Create workspace'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
