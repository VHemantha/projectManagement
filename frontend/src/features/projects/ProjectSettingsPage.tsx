import { type FormEvent, useState } from 'react'
import { Trash2 } from 'lucide-react'

import styles from './ProjectSettingsPage.module.css'
import { useProjectContext } from './useProjectContext'
import { useAddMember, useProjectBoard, useRemoveMember, useUpdateMemberRole, useUpdateProject } from '@/api/projects'
import { useUsers } from '@/api/users'
import { Avatar, Button, Input, StatusBadge, Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'
import type { StatusCategory } from '@/design-system'

function GeneralTab() {
  const { project } = useProjectContext()
  const [name, setName] = useState(project.name)
  const [description, setDescription] = useState(project.description)
  const updateProject = useUpdateProject(project.key)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    updateProject.mutate({ name, description })
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
      </Tabs>
    </div>
  )
}
