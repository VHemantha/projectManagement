import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2 } from 'lucide-react'

import { Plus } from 'lucide-react'

import styles from './ProjectSettingsPage.module.css'
import { CreateClientDialog } from './CreateClientDialog'
import { TaskNamesEditor } from './TaskNamesEditor'
import { useCanConfigureBoard } from '@/features/board/boardPermissions'
import { BoardSettingsForm } from '@/features/board/BoardSettingsPanel'
import { useProjectContext } from './useProjectContext'
import { isScrumWorkspace, workspaceUrl } from './workspaceTabs'
import { useUpdateWorkflowTransition, useWorkflowTransitions } from '@/api/boards'
import { extractErrorMessage } from '@/api/errors'
import { useClients } from '@/api/clients'
import {
  useAddMember,
  useCreateLabel,
  useProjectBoard,
  useRemoveMember,
  useUpdateLabel,
  useUpdateMemberRole,
  useUpdateProject,
} from '@/api/projects'
import { useTeams } from '@/api/teams'
import { useUsers } from '@/api/users'
import { Avatar, Button, InlineEdit, Input, StatusBadge, Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'
import type { StatusCategory } from '@/design-system'
import { CATEGORY_LABELS } from '@/lib/text'

function GeneralTab() {
  const { project } = useProjectContext()
  const navigate = useNavigate()
  const [key, setKey] = useState(project.key)
  const [name, setName] = useState(project.name)
  const [description, setDescription] = useState(project.description)
  const [clientId, setClientId] = useState(project.client?.id ?? '')
  const [createClientOpen, setCreateClientOpen] = useState(false)
  const [primaryTeamId, setPrimaryTeamId] = useState(project.primary_team?.id ?? '')
  const [contributingIds, setContributingIds] = useState<number[]>(project.contributing_teams.map((t) => t.id))
  const [budgetedHours, setBudgetedHours] = useState(project.budgeted_hours != null ? String(project.budgeted_hours) : '')
  const [jobValue, setJobValue] = useState(project.job_value ?? '')
  const [jobValueCurrency, setJobValueCurrency] = useState(project.job_value_currency)
  const updateProject = useUpdateProject(project.key)
  const { data: clients } = useClients()
  const { data: teams } = useTeams()

  const keyChanged = key !== project.key
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    updateProject.mutate(
      {
      ...(keyChanged ? { key } : {}),
      name,
      description,
      client_id: clientId ? Number(clientId) : null,
      primary_team_id: primaryTeamId ? Number(primaryTeamId) : null,
      contributing_team_ids: contributingIds,
      budgeted_hours: budgetedHours ? Number(budgetedHours) : null,
      job_value: jobValue ? jobValue : null,
      job_value_currency: jobValueCurrency,
      },
      {
        // The project now lives at its new key; stay on its settings.
        onSuccess: (saved) => {
          if (saved.key !== project.key) navigate(workspaceUrl(saved.key, 'settings'), { replace: true })
        },
      },
    )
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div>
        <Input
          id="settings-key"
          label="Key"
          value={key}
          maxLength={100}
          disabled={!project.can_manage}
          onChange={(e) => setKey(e.target.value.replace(/[^A-Za-z0-9]/g, ''))}
        />
        {keyChanged && key && (
          <div className={styles.keyWarning} role="note">
            Saving renames every job in this workspace ({project.key}-12 becomes {key}-12). Old links and keys
            keep working.
          </div>
        )}
      </div>
      <Input
        id="settings-name"
        label="Name"
        value={name}
        disabled={!project.can_manage}
        onChange={(e) => setName(e.target.value)}
      />
      <Input
        id="settings-description"
        label="Description"
        value={description}
        disabled={!project.can_manage}
        onChange={(e) => setDescription(e.target.value)}
      />

      <div>
        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Client</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <select
            className={styles.roleSelect}
            style={{ width: '100%', height: 36 }}
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
          >
            <option value="">No client (internal)</option>
            {clients?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <Button type="button" variant="subtle" size="sm" onClick={() => setCreateClientOpen(true)}>
            <Plus size={14} /> New
          </Button>
        </div>
        <CreateClientDialog
          open={createClientOpen}
          onOpenChange={setCreateClientOpen}
          onCreated={(client) => setClientId(client.id)}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Primary team</label>
        <select
          className={styles.roleSelect}
          style={{ width: '100%', height: 36 }}
          value={primaryTeamId}
          onChange={(e) => setPrimaryTeamId(e.target.value)}
        >
          <option value="">No team</option>
          {teams?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
          Other contributing teams
        </label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
          {teams
            ?.filter((t) => String(t.id) !== String(primaryTeamId))
            .map((t) => (
              <label key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={contributingIds.includes(t.id)}
                  onChange={() =>
                    setContributingIds((prev) =>
                      prev.includes(t.id) ? prev.filter((id) => id !== t.id) : [...prev, t.id],
                    )
                  }
                />
                {t.name}
              </label>
            ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <Input
          id="settings-budgeted-hours"
          label="Budgeted hours"
          type="number"
          min={0}
          value={budgetedHours}
          disabled={!project.can_manage}
          title={project.can_manage ? undefined : 'Only the workspace lead or an admin can change the budget.'}
          onChange={(e) => setBudgetedHours(e.target.value)}
        />
        <Input
          id="settings-job-value"
          label="Job value"
          type="number"
          min={0}
          step="0.01"
          value={jobValue}
          onChange={(e) => setJobValue(e.target.value)}
        />
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Currency</label>
          <select
            className={styles.roleSelect}
            style={{ height: 36 }}
            value={jobValueCurrency}
            onChange={(e) => setJobValueCurrency(e.target.value)}
          >
            {['USD', 'EUR', 'GBP', 'INR'].map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className={styles.hint}>
        Reporting/visibility only — TrackFlow doesn&apos;t generate invoices or handle billing.
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Button type="submit" variant="primary" disabled={updateProject.isPending}>
          {updateProject.isPending ? 'Saving…' : 'Save changes'}
        </Button>
        {updateProject.isSuccess && <span className={styles.savedMsg}>Saved</span>}
      </div>
      {updateProject.isError && (
        <div role="alert" style={{ color: 'var(--tf-danger)', fontSize: 13 }}>
          {extractErrorMessage(updateProject.error).replace(/^\w+: /, '')}
        </div>
      )}
    </form>
  )
}

function PeopleTab() {
  const { project } = useProjectContext()
  const { data: users } = useUsers()
  const addMember = useAddMember(project.key)
  const updateRole = useUpdateMemberRole(project.key)
  const removeMember = useRemoveMember(project.key)
  const [pickedUserId, setPickedUserId] = useState('')

  const existingIds = new Set(project.memberships.map((m) => m.user.id))
  const candidates = (users ?? []).filter((u) => !existingIds.has(u.id))

  return (
    <div>
      <div className={styles.addMemberRow}>
        <div style={{ flex: 1 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Add member</label>
          <select
            className={styles.roleSelect}
            style={{ width: '100%', height: 36 }}
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
        <Button
          variant="secondary"
          disabled={!pickedUserId || addMember.isPending}
          onClick={() => {
            addMember.mutate({ user_id: Number(pickedUserId), role: 'member' })
            setPickedUserId('')
          }}
        >
          Add
        </Button>
      </div>

      {project.memberships.map((m) => (
        <div key={m.id} className={styles.memberRow}>
          <Avatar name={m.user.display_name} src={m.user.avatar} size={32} />
          <div>
            <div className={styles.memberName}>{m.user.display_name}</div>
            <div className={styles.memberEmail}>{m.user.email}</div>
          </div>
          <select
            className={styles.roleSelect}
            value={m.role}
            onChange={(e) => updateRole.mutate({ id: m.id, role: e.target.value })}
          >
            <option value="admin">Admin</option>
            <option value="member">Member</option>
            <option value="viewer">Viewer</option>
          </select>
          <Button variant="subtle" iconOnly size="sm" onClick={() => removeMember.mutate(m.id)} aria-label="Remove member">
            <Trash2 size={14} />
          </Button>
        </div>
      ))}
    </div>
  )
}

const REASSIGN_LABELS: Record<string, string> = {
  no_change: 'No change',
  preparer: 'Set to preparer',
  reviewer: 'Set to reviewer',
  assignee: 'Set to assignee',
}

function TransitionRulesTab() {
  const { project } = useProjectContext()
  const { data: transitions } = useWorkflowTransitions(project.key)
  const updateTransition = useUpdateWorkflowTransition(project.key)

  return (
    <div>
      <div className={styles.hint}>
        When an issue moves through one of these transitions, optionally auto-set who&apos;s
        currently responsible for it (e.g. moving to review hands it to the reviewer).
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: '6px 8px', fontSize: 11, color: 'var(--tf-text-subtle)' }}>
              Transition
            </th>
            <th style={{ textAlign: 'left', padding: '6px 8px', fontSize: 11, color: 'var(--tf-text-subtle)' }}>
              On this transition, set current responsible to
            </th>
          </tr>
        </thead>
        <tbody>
          {transitions?.map((t) => (
            <tr key={t.id} style={{ borderTop: '1px solid var(--tf-border)' }}>
              <td style={{ padding: '8px' }}>
                {t.from_status_name} → {t.to_status_name}
              </td>
              <td style={{ padding: '8px' }}>
                <select
                  className={styles.roleSelect}
                  value={t.set_current_responsible_to}
                  onChange={(e) => updateTransition.mutate({ id: t.id, set_current_responsible_to: e.target.value })}
                >
                  {Object.entries(REASSIGN_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function WorkflowTab() {
  const { project } = useProjectContext()
  const { data: board } = useProjectBoard(project.key)

  return (
    <div>
      <div className={styles.hint}>
        This project&apos;s statuses. To add a new stage, add a column in the Board tab — saving it
        creates the status. Unused statuses can be deleted there too.
      </div>
      {board?.statuses.map((s) => (
        <div key={s.id} className={styles.statusRow}>
          <span className={styles.statusName}>{s.name}</span>
          <StatusBadge label={CATEGORY_LABELS[s.category]} category={s.category as StatusCategory} />
        </div>
      ))}
    </div>
  )
}

function BoardTab() {
  const { project } = useProjectContext()
  const { data: board } = useProjectBoard(project.key)
  const canConfigure = useCanConfigureBoard(project)

  if (!board) return null
  if (!canConfigure) {
    return (
      <div className={styles.hint}>
        Only the workspace lead, a workspace admin or an organisation admin can customise this board.
      </div>
    )
  }
  return (
    <div>
      <div className={styles.hint}>
        Customise the {isScrumWorkspace(project) ? 'Scrum sprint' : 'Kanban'} board: add or reorder columns,
        colour them, set WIP limits and choose how cards are coloured.
      </div>
      <BoardSettingsForm key={board.id} board={board} projectKey={project.key} />
    </div>
  )
}

function TasksTab() {
  const { project } = useProjectContext()
  const [taskNames, setTaskNames] = useState<string[]>(project.task_names)
  const updateProject = useUpdateProject(project.key)
  const dirty = JSON.stringify(taskNames) !== JSON.stringify(project.task_names)

  return (
    <div className={styles.form}>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--tf-text-subtle)' }}>
        These task names are offered as the summary when creating a job in {project.name}. Changing
        the list doesn&apos;t rename existing jobs.
      </p>
      <TaskNamesEditor id="settings-tasks" value={taskNames} onChange={setTaskNames} />
      {updateProject.isError && (
        <div style={{ color: 'var(--tf-danger)', fontSize: 13 }}>{extractErrorMessage(updateProject.error)}</div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Button
          variant="primary"
          disabled={!dirty || updateProject.isPending}
          onClick={() => updateProject.mutate({ task_names: taskNames })}
        >
          {updateProject.isPending ? 'Saving…' : 'Save tasks'}
        </Button>
        {!dirty && updateProject.isSuccess && (
          <span style={{ fontSize: 13, color: 'var(--tf-text-subtle)' }}>Saved.</span>
        )}
      </div>
    </div>
  )
}

const LABEL_COLORS = ['#DCDFE4', '#DEEBFF', '#DCFCE7', '#FFEDD5', '#FCE7F3', '#EDE9FE', '#CCFBF1', '#FFF7D6']

function LabelsTab() {
  const { project } = useProjectContext()
  const updateLabel = useUpdateLabel(project.key)
  const createLabel = useCreateLabel(project.key)
  const [newName, setNewName] = useState('')
  const canEdit = project.can_manage

  return (
    <div className={styles.form}>
      <p className={styles.hint} style={{ margin: 0 }}>
        Labels tag jobs in {project.name}.{' '}
        {canEdit ? 'Click a name to rename it everywhere it is used.' : 'Only the workspace lead or an admin can change them.'}
      </p>
      {project.labels.length === 0 && <p className={styles.hint}>No labels yet.</p>}
      <ul className={styles.labelList} aria-label="Labels">
        {project.labels.map((label) => (
          <li key={label.id} className={styles.labelRow}>
            <span className={styles.labelSwatch} style={{ background: label.color }} aria-hidden="true" />
            <InlineEdit
              value={label.name}
              label="Label name"
              maxLength={60}
              canEdit={canEdit}
              onSave={(name) => updateLabel.mutateAsync({ id: label.id, name })}
            />
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className={styles.labelAdd}
          onSubmit={(e) => {
            e.preventDefault()
            const name = newName.trim()
            if (!name) return
            const color = LABEL_COLORS[project.labels.length % LABEL_COLORS.length]
            createLabel.mutate({ name, color }, { onSuccess: () => setNewName('') })
          }}
        >
          <Input
            id="new-label"
            aria-label="New label name"
            placeholder="New label"
            maxLength={60}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <Button type="submit" variant="subtle" disabled={!newName.trim() || createLabel.isPending}>
            <Plus size={14} /> Add label
          </Button>
        </form>
      )}
      {createLabel.isError && (
        <div role="alert" style={{ color: 'var(--tf-danger)', fontSize: 13 }}>
          {extractErrorMessage(createLabel.error)}
        </div>
      )}
    </div>
  )
}

export function ProjectSettingsPage() {
  const { project } = useProjectContext()

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{project.name} settings</h1>
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="board">Board</TabsTrigger>
          <TabsTrigger value="tasks">Tasks</TabsTrigger>
          <TabsTrigger value="labels">Labels</TabsTrigger>
          <TabsTrigger value="people">People</TabsTrigger>
          <TabsTrigger value="workflow">Workflow</TabsTrigger>
          <TabsTrigger value="transitions">Transition rules</TabsTrigger>
        </TabsList>
        <TabsContent value="general">
          <GeneralTab />
        </TabsContent>
        <TabsContent value="board">
          <BoardTab />
        </TabsContent>
        <TabsContent value="tasks">
          <TasksTab />
        </TabsContent>
        <TabsContent value="labels">
          <LabelsTab />
        </TabsContent>
        <TabsContent value="people">
          <PeopleTab />
        </TabsContent>
        <TabsContent value="workflow">
          <WorkflowTab />
        </TabsContent>
        <TabsContent value="transitions">
          <TransitionRulesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
