import { useState } from 'react'

import { useChannel, useLinkTaskToMessage } from '@/api/chat'
import { useIssues } from '@/api/issues'
import type { ChatMessage } from '@/api/types'
import { Button, Dialog, DialogContent, IssueKey, IssueTypeIcon } from '@/design-system'

interface LinkTaskToMessageDialogProps {
  message: ChatMessage
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function LinkTaskToMessageDialog({ message, open, onOpenChange }: LinkTaskToMessageDialogProps) {
  const { data: channel } = useChannel(open ? message.channel : undefined)
  const [search, setSearch] = useState('')
  const { data: results } = useIssues(
    { project: channel?.project_key ?? undefined, search, page_size: 8 },
    open && search.length >= 2,
  )
  const linkTask = useLinkTaskToMessage()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Link to existing task" maxWidth={460}>
        <input
          autoFocus
          placeholder="Search by key or summary…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%',
            height: 36,
            borderRadius: 4,
            border: '2px solid var(--tf-border)',
            padding: '0 10px',
            marginBottom: 12,
          }}
        />
        <div>
          {results?.results.map((issue) => (
            <div
              key={issue.id}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 4px', cursor: 'pointer', fontSize: 13 }}
              onClick={() =>
                linkTask.mutate(
                  { messageId: message.id, issueId: issue.id },
                  { onSuccess: () => onOpenChange(false) },
                )
              }
            >
              <IssueTypeIcon typeName={issue.issue_type.name} size={14} />
              <IssueKey value={issue.key} />
              <span>{issue.summary}</span>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
          <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
