import { useState } from 'react'

import { extractErrorMessage } from '@/api/errors'
import { useCreateClient, useUpdateClient, type ClientItem } from '@/api/clients'
import { useTeams } from '@/api/teams'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

interface CreateClientDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (client: ClientItem) => void
  /** Edit this sub-workspace instead of creating a new one. */
  client?: ClientItem
  /** The workspace a new sub-workspace starts in (e.g. the one it was created from). */
  defaultTeamId?: number
}

/** Create or edit a sub-workspace (a client in the API) — which workspace it is in, and whether
 * its tasks must belong to a project. */
export function CreateClientDialog({ open, onOpenChange, onCreated, client, defaultTeamId }: CreateClientDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={client ? `${client.name} settings` : 'New sub-workspace'} maxWidth={440}>
        {/* Mounted per opening so the form always starts from the sub-workspace's current values. */}
        {open && (
          <ClientForm client={client} defaultTeamId={defaultTeamId} onDone={() => onOpenChange(false)} onCreated={onCreated} />
        )}
      </DialogContent>
    </Dialog>
  )
}

const selectStyle: React.CSSProperties = {
  width: '100%',
  height: 36,
  borderRadius: 4,
  border: '1px solid var(--tf-border)',
  padding: '0 10px',
  fontSize: 13,
  background: 'var(--tf-surface)',
  color: 'var(--tf-text)',
}

function ClientForm({
  client,
  defaultTeamId,
  onDone,
  onCreated,
}: {
  client?: ClientItem
  defaultTeamId?: number
  onDone: () => void
  onCreated?: (client: ClientItem) => void
}) {
  const [name, setName] = useState(client?.name ?? '')
  const [teamId, setTeamId] = useState(String(client ? (client.team_id ?? '') : (defaultTeamId ?? '')))
  const [contactName, setContactName] = useState(client?.primary_contact_name ?? '')
  const [contactEmail, setContactEmail] = useState(client?.primary_contact_email ?? '')
  const [requiresProjects, setRequiresProjects] = useState(client?.requires_projects ?? false)
  const { data: teams } = useTeams()
  const createClient = useCreateClient()
  const updateClient = useUpdateClient()
  const mutation = client ? updateClient : createClient

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    const payload = {
      name: name.trim(),
      team_id: teamId ? Number(teamId) : null,
      primary_contact_name: contactName.trim(),
      primary_contact_email: contactEmail.trim(),
      requires_projects: requiresProjects,
    }
    if (client) {
      updateClient.mutate({ id: client.id, ...payload }, { onSuccess: onDone })
    } else {
      createClient.mutate(payload, {
        onSuccess: (created) => {
          onDone()
          onCreated?.(created)
        },
      })
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Input
        id="client-name"
        label="Sub-workspace name"
        required
        autoFocus
        placeholder="e.g. RWCA"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <div>
        <label htmlFor="client-team" style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
          Workspace
        </label>
        <select id="client-team" style={selectStyle} value={teamId} onChange={(e) => setTeamId(e.target.value)}>
          <option value="">Not in a workspace yet</option>
          {teams?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>
      <Input
        id="client-contact-name"
        label="Primary contact (optional)"
        value={contactName}
        onChange={(e) => setContactName(e.target.value)}
      />
      <Input
        id="client-contact-email"
        label="Contact email (optional)"
        type="email"
        value={contactEmail}
        onChange={(e) => setContactEmail(e.target.value)}
      />
      <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13 }}>
        <input
          type="checkbox"
          checked={requiresProjects}
          onChange={(e) => setRequiresProjects(e.target.checked)}
          style={{ marginTop: 2 }}
        />
        <span>
          <strong>Requires projects</strong>
          <br />
          <span style={{ color: 'var(--tf-text-subtle)' }}>
            When off, tasks can be added to this sub-workspace directly, without creating a project first.
          </span>
        </span>
      </label>
      {mutation.isError && (
        <div role="alert" style={{ color: 'var(--tf-danger)', fontSize: 13 }}>
          {extractErrorMessage(mutation.error)}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button type="button" variant="subtle" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={!name.trim() || mutation.isPending}>
          {client ? 'Save' : 'Create'}
        </Button>
      </div>
    </form>
  )
}
