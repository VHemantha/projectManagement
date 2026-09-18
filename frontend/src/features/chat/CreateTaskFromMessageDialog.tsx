import { useEffect, useState } from 'react'

import { extractPlainText } from './richTextPlainText'
import { useChannel, useCreateTaskFromMessage } from '@/api/chat'
import { useIssueTypes } from '@/api/issues'
import { useProjects } from '@/api/projects'
import type { ChatMessage } from '@/api/types'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

interface CreateTaskFromMessageDialogProps {
  message: ChatMessage
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateTaskFromMessageDialog({ message, open, onOpenChange }: CreateTaskFromMessageDialogProps) {
  const { data: channel } = useChannel(open ? message.channel : undefined)
  const { data: projects } = useProjects()
  const [projectKey, setProjectKey] = useState('')
  const { data: issueTypes } = useIssueTypes(projectKey || undefined, false)
  const [issueTypeId, setIssueTypeId] = useState('')
  const [summary, setSummary] = useState('')
  const createTask = useCreateTaskFromMessage()

  useEffect(() => {
    if (open) {
      setSummary(extractPlainText(message.body, 200))
      setProjectKey(channel?.project_key ?? projects?.[0]?.key ?? '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, channel])

  useEffect(() => {
    if (issueTypes && issueTypes.length > 0 && !issueTypes.some((t) => String(t.id) === issueTypeId)) {
      setIssueTypeId(String(issueTypes[0].id))
    }
  }, [issueTypes, issueTypeId])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectKey || !issueTypeId || !summary.trim()) return
    createTask.mutate(
      { messageId: message.id, project: projectKey, summary: summary.trim(), issue_type_id: Number(issueTypeId) },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Create task from message" maxWidth={460}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Project</label>
              <select
                style={{ width: '100%', height: 36, borderRadius: 4, border: '2px solid var(--tf-border)', padding: '0 10px' }}
                value={projectKey}
                onChange={(e) => setProjectKey(e.target.value)}
              >
                {projects?.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Type</label>
              <select
                style={{ width: '100%', height: 36, borderRadius: 4, border: '2px solid var(--tf-border)', padding: '0 10px' }}
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
          <Input id="ctm-summary" label="Summary" required value={summary} onChange={(e) => setSummary(e.target.value)} />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!summary.trim() || createTask.isPending}>
              {createTask.isPending ? 'Creating…' : 'Create task'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
