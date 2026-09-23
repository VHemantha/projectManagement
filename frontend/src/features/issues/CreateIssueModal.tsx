import type { JSONContent } from '@tiptap/react'
import { useEffect, useState } from 'react'

import styles from './CreateIssueModal.module.css'
import { useClients } from '@/api/clients'
import { extractErrorMessage } from '@/api/errors'
import { useCreateIssue, useIssueTypes, useIssues } from '@/api/issues'
import { useProject, useProjects } from '@/api/projects'
import { useTeam, useTeams } from '@/api/teams'
import type { Priority } from '@/api/types'
import { useUsers } from '@/api/users'
import { Button, Dialog, DialogContent, Input, RichTextEditor } from '@/design-system'
import { useUiStore } from '@/store/uiStore'

const PRIORITIES: Priority[] = ['highest', 'high', 'medium', 'low', 'lowest']

export function CreateIssueModal() {
  const open = useUiStore((s) => s.createIssueOpen)
  const defaultProjectKey = useUiStore((s) => s.createIssueDefaultProjectKey)
  const closeCreateIssue = useUiStore((s) => s.closeCreateIssue)
  const openIssueModal = useUiStore((s) => s.openIssueModal)

  const { data: projects } = useProjects()
  const { data: teams } = useTeams()
  const { data: clients } = useClients()
  const [teamId, setTeamId] = useState('')
  const [clientId, setClientId] = useState('')
  const [projectKey, setProjectKey] = useState<string>('')
  const { data: project } = useProject(projectKey || undefined)
  const { data: issueTypes } = useIssueTypes(projectKey || undefined, false)
  const { data: users } = useUsers()
  const { data: selectedTeam } = useTeam(teamId ? Number(teamId) : undefined)
  const { data: epicsPage } = useIssues({ project: projectKey, issue_type: 'Epic', page_size: 100 }, !!projectKey)
  const epics = epicsPage?.results ?? []
  const createIssue = useCreateIssue()

  const [issueTypeId, setIssueTypeId] = useState<string>('')
  const [summary, setSummary] = useState('')
  const [description, setDescription] = useState<JSONContent | null>(null)
  const [assigneeId, setAssigneeId] = useState('')
  const [priority, setPriority] = useState<Priority>('medium')
  const [storyPoints, setStoryPoints] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [epicId, setEpicId] = useState('')
  const [labelIds, setLabelIds] = useState<number[]>([])
  const [createAnother, setCreateAnother] = useState(false)

  // Team + Client narrow which projects are offered, cascading Team -> Client -> Project;
  // the issue itself stays project-centric (project.primary_team/client remain the source of
  // truth), these pickers just make it faster to find the right project. Client options list
  // every client that exists (not just ones some project already happens to be attached to) —
  // a client with no project yet still needs to be pickable so its gap is visible, rather than
  // silently missing from the dropdown.
  const clientOptions = clients ?? []
  const projectsInTeam = teamId
    ? (projects ?? []).filter((p) => p.primary_team?.id === Number(teamId))
    : (projects ?? [])
  const availableProjects = clientId
    ? projectsInTeam.filter((p) => p.client?.id === Number(clientId))
    : projectsInTeam

  // Assignee is restricted to the selected team's members once a team is chosen.
  const assigneeCandidates = selectedTeam ? selectedTeam.memberships.map((m) => m.user) : (users ?? [])

  useEffect(() => {
    if (open && !projectKey && projects && projects.length > 0) {
      setProjectKey(defaultProjectKey ?? projects[0].key)
    }
  }, [open, projects, defaultProjectKey, projectKey])

  useEffect(() => {
    if (!availableProjects.some((p) => p.key === projectKey)) {
      setProjectKey(availableProjects[0]?.key ?? '')
    }
  }, [teamId, clientId, availableProjects, projectKey])

  useEffect(() => {
    if (issueTypes && issueTypes.length > 0 && !issueTypes.some((t) => String(t.id) === issueTypeId)) {
      setIssueTypeId(String(issueTypes[0].id))
    }
  }, [issueTypes, issueTypeId])

  useEffect(() => {
    if (assigneeId && !assigneeCandidates.some((u) => String(u.id) === assigneeId)) {
      setAssigneeId('')
    }
  }, [teamId, assigneeId, assigneeCandidates])

  const resetFields = () => {
    setSummary('')
    setDescription(null)
    setAssigneeId('')
    setPriority('medium')
    setStoryPoints('')
    setDueDate('')
    setEpicId('')
    setLabelIds([])
  }

  const handleClose = () => {
    closeCreateIssue()
    setProjectKey('')
    setTeamId('')
    setClientId('')
    resetFields()
    setCreateAnother(false)
    createIssue.reset()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectKey || !issueTypeId || !summary.trim()) return
    createIssue.mutate(
      {
        project: projectKey,
        issue_type_id: Number(issueTypeId),
        summary: summary.trim(),
        description,
        assignee_id: assigneeId ? Number(assigneeId) : null,
        priority,
        story_points: storyPoints ? Number(storyPoints) : null,
        due_date: dueDate || null,
        epic_id: epicId ? Number(epicId) : null,
        label_ids: labelIds,
      },
      {
        onSuccess: (issue) => {
          if (createAnother) {
            resetFields()
          } else {
            closeCreateIssue()
            openIssueModal(issue.key)
            setProjectKey('')
            resetFields()
          }
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : handleClose())}>
      <DialogContent title="Create issue" maxWidth={560}>
        <form className={styles.form} onSubmit={handleSubmit}>
          {createIssue.isError && (
            <div className={styles.formError}>{extractErrorMessage(createIssue.error)}</div>
          )}

          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ci-team">
                Team
              </label>
              <select
                id="ci-team"
                className={styles.select}
                value={teamId}
                onChange={(e) => {
                  setTeamId(e.target.value)
                  setClientId('')
                }}
              >
                <option value="">Any team</option>
                {teams?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ci-client">
                Client
              </label>
              <select
                id="ci-client"
                className={styles.select}
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
              >
                <option value="">Any client</option>
                {clientOptions.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ci-project">
                Project
              </label>
              <select
                id="ci-project"
                className={styles.select}
                value={projectKey}
                onChange={(e) => setProjectKey(e.target.value)}
              >
                {availableProjects.length === 0 && <option value="">No project for this team/client yet</option>}
                {availableProjects.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.name} ({p.key})
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ci-type">
                Issue type
              </label>
              <select
                id="ci-type"
                className={styles.select}
                value={issueTypeId}
                onChange={(e) => setIssueTypeId(e.target.value)}
              >
                {issueTypes?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <Input
            id="ci-summary"
            label="Summary"
            required
            autoFocus
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="What needs to be done?"
          />

          <div className={styles.field}>
            <label className={styles.label}>Description</label>
            <RichTextEditor content={description} onChange={setDescription} editable placeholder="Add a description…" />
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ci-assignee">
                Assignee
              </label>
              <select
                id="ci-assignee"
                className={styles.select}
                value={assigneeId}
                onChange={(e) => setAssigneeId(e.target.value)}
              >
                <option value="">Unassigned</option>
                {assigneeCandidates.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.display_name}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ci-priority">
                Priority
              </label>
              <select
                id="ci-priority"
                className={styles.select}
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p[0].toUpperCase() + p.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className={styles.row}>
            <Input
              id="ci-points"
              label="Story points"
              type="number"
              min={0}
              value={storyPoints}
              onChange={(e) => setStoryPoints(e.target.value)}
            />
            <Input
              id="ci-due"
              label="Due date"
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </div>

          {epics.length > 0 && (
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ci-epic">
                Epic
              </label>
              <select
                id="ci-epic"
                className={styles.select}
                value={epicId}
                onChange={(e) => setEpicId(e.target.value)}
              >
                <option value="">No epic</option>
                {epics.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.summary}
                  </option>
                ))}
              </select>
            </div>
          )}

          {project && project.labels.length > 0 && (
            <div className={styles.field}>
              <label className={styles.label}>Labels</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {project.labels.map((l) => {
                  const checked = labelIds.includes(l.id)
                  return (
                    <label key={l.id} className={styles.checkboxLabel}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) =>
                          setLabelIds((prev) =>
                            e.target.checked ? [...prev, l.id] : prev.filter((id) => id !== l.id),
                          )
                        }
                      />
                      {l.name}
                    </label>
                  )
                })}
              </div>
            </div>
          )}

          <div className={styles.footer}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={createAnother}
                onChange={(e) => setCreateAnother(e.target.checked)}
              />
              Create another
            </label>
            <div className={styles.actions}>
              <Button type="button" variant="subtle" onClick={handleClose}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={createIssue.isPending || !summary.trim() || !projectKey}>
                {createIssue.isPending ? 'Creating…' : 'Create'}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
