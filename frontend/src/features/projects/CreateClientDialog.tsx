import { useState } from 'react'

import { extractErrorMessage } from '@/api/errors'
import { useCreateClient, useUpdateClient, type ClientItem } from '@/api/clients'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

interface CreateClientDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (client: ClientItem) => void
  /** Edit this client instead of creating a new one. */
  client?: ClientItem
}

/** Create or edit a client — including whether its jobs must belong to a project. */
export function CreateClientDialog({ open, onOpenChange, onCreated, client }: CreateClientDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={client ? `${client.name} settings` : 'New client'} maxWidth={440}>
        {/* Mounted per opening so the form always starts from the client's current values. */}
        {open && <ClientForm client={client} onDone={() => onOpenChange(false)} onCreated={onCreated} />}
      </DialogContent>
    </Dialog>
  )
}

function ClientForm({
  client,
  onDone,
  onCreated,
}: {
  client?: ClientItem
  onDone: () => void
  onCreated?: (client: ClientItem) => void
}) {
  const [name, setName] = useState(client?.name ?? '')
  const [contactName, setContactName] = useState(client?.primary_contact_name ?? '')
  const [contactEmail, setContactEmail] = useState(client?.primary_contact_email ?? '')
  const [requiresProjects, setRequiresProjects] = useState(client?.requires_projects ?? false)
  const createClient = useCreateClient()
  const updateClient = useUpdateClient()
  const mutation = client ? updateClient : createClient

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    const payload = {
      name: name.trim(),
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
        label="Client name"
        required
        autoFocus
        placeholder="e.g. Acme Corp"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
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
            When off, jobs can be added for this client directly, without creating a project first.
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
