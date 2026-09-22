import { type FormEvent, useState } from 'react'
import { Trash2 } from 'lucide-react'

import { Plus } from 'lucide-react'

import styles from './ProjectSettingsPage.module.css'
import { CreateClientDialog } from './CreateClientDialog'
import { useProjectContext } from './useProjectContext'
import { useUpdateWorkflowTransition, useWorkflowTransitions } from '@/api/boards'
import { useClients } from '@/api/clients'
import { useAddMember, useProjectBoard, useRemoveMember, useUpdateMemberRole, useUpdateProject } from '@/api/projects'
import { useTeams } from '@/api/teams'
import { useUsers } from '@/api/users'
import { Avatar, Button, Input, StatusBadge, Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'
import type { StatusCategory } from '@/design-system'

function GeneralTab() {
  const { project } = useProjectContext()
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

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    updateProject.mutate({
      name,
      description,
      client_id: clientId ? Number(clientId) : null,
      primary_team_id: primaryTeamId ? Number(primaryTeamId) : null,
      contributing_team_ids: contributingIds,
      budgeted_hours: budgetedHours ? Number(budgetedHours) : null,
      job_value: jobValue ? jobValue : null,
      job_value_currency: jobValueCurrency,
    })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <Input id="settings-key" label="Key" value={project.key} disabled />
      <Input id="settings-name" label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <Input
        id="settings-description"
        label="Description"
        value={description}
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
            <th style={{ textAlign: 'left', padding: '6px 8px', fontSize: 11, color: 'var(--tf-text-subtle)', textTransform: 'uppercase' }}>
              Transition
            </th>
            <th style={{ textAlign: 'left', padding: '6px 8px', fontSize: 11, color: 'var(--tf-text-subtle)', textTransform: 'uppercase' }}>
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
        Read-only view of this project&apos;s status pipeline. Full drag-to-reorder and custom
        transitions are a fast-follow — statuses currently mirror the board columns.
      </div>
      {board?.statuses.map((s) => (
        <div key={s.id} className={styles.statusRow}>
          <span className={styles.statusName}>{s.name}</span>
          <StatusBadge label={s.category.replace('_', ' ')} category={s.category as StatusCategory} />
        </div>
      ))}
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
          <TabsTrigger value="people">People</TabsTrigger>
          <TabsTrigger value="workflow">Workflow</TabsTrigger>
          <TabsTrigger value="transitions">Transition rules</TabsTrigger>
        </TabsList>
        <TabsContent value="general">
          <GeneralTab />
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
