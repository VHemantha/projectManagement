import { useState } from 'react'

import { useCreateChannel } from '@/api/chat'
import type { Channel } from '@/api/types'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

interface CreateChannelDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (channel: Channel) => void
}

export function CreateChannelDialog({ open, onOpenChange, onCreated }: CreateChannelDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const createChannel = useCreateChannel()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createChannel.mutate(
      { name: name.trim().toLowerCase().replace(/\s+/g, '-'), description, channel_type: 'topic' },
      {
        onSuccess: (channel) => {
          onOpenChange(false)
          setName('')
          setDescription('')
          onCreated(channel)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Create channel" maxWidth={420}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input
            id="channel-name"
            label="Channel name"
            required
            autoFocus
            placeholder="e.g. random"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            id="channel-description"
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!name.trim() || createChannel.isPending}>
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
