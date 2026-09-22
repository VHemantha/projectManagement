import { useState } from 'react'

import { useCreateClient, type ClientItem } from '@/api/clients'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

interface CreateClientDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (client: ClientItem) => void
}

export function CreateClientDialog({ open, onOpenChange, onCreated }: CreateClientDialogProps) {
  const [name, setName] = useState('')
  const [contactName, setContactName] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const createClient = useCreateClient()

  const reset = () => {
    setName('')
    setContactName('')
    setContactEmail('')
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createClient.mutate(
      { name: name.trim(), primary_contact_name: contactName.trim(), primary_contact_email: contactEmail.trim() },
      {
        onSuccess: (client) => {
          onOpenChange(false)
          reset()
          onCreated?.(client)
        },
      },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) reset()
      }}
    >
      <DialogContent title="New client" maxWidth={420}>
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
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!name.trim() || createClient.isPending}>
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
