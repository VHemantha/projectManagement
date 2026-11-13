import { useId, useState } from 'react'

import { extractErrorMessage } from '@/api/errors'
import { useDeleteIssue } from '@/api/issues'
import { Button, Dialog, DialogContent, Input } from '@/design-system'

export const CONFIRM_WORD = 'DELETE'

/** "Delete this task?" — permanent, so the person types DELETE before the button works (AFIT,
 * 13 Nov 2026). Used by the card's "…" menu on the board and by the opened task. */
export function DeleteTaskDialog({ issue, open, onOpenChange, onDeleted }: {
  issue: { key: string; summary: string }
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted?: () => void
}) {
  const remove = useDeleteIssue()
  const [typed, setTyped] = useState('')
  const inputId = useId()
  const confirmed = typed.trim() === CONFIRM_WORD

  const change = (next: boolean) => {
    if (!next) {
      setTyped('')
      remove.reset()
    }
    onOpenChange(next)
  }
  const submit = () => {
    if (!confirmed || remove.isPending) return
    remove.mutate(issue.key, {
      onSuccess: () => {
        change(false)
        onDeleted?.()
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent title="Delete this task?" maxWidth={460}>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <p style={{ margin: '0 0 8px' }}>
            <strong>{issue.summary}</strong> ({issue.key}) will be deleted permanently, with its sub-tasks, comments, attachments,
            history, AI pre-check runs and coordinator follow-ups. This can&apos;t be undone.
          </p>
          <p style={{ margin: '0 0 12px', color: 'var(--tf-text-secondary)', fontSize: 13 }}>
            Hours already logged on it stay in timesheets, without the task. To keep the task&apos;s record, move it to To be
            Archived instead.
          </p>
          <Input
            id={inputId}
            label={`Type ${CONFIRM_WORD} to confirm`}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            autoFocus
            placeholder={CONFIRM_WORD}
          />
          {remove.isError && (
            <p role="alert" style={{ margin: '12px 0 0', color: 'var(--tf-danger)', fontSize: 13 }}>
              {extractErrorMessage(remove.error, 'The task could not be deleted.')}
            </p>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <Button type="button" variant="secondary" onClick={() => change(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" disabled={!confirmed || remove.isPending}>
              {remove.isPending ? 'Deleting…' : 'Delete permanently'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
