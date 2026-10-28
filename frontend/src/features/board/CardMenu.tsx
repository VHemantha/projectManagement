import { MoreHorizontal, Trash2 } from 'lucide-react'
import { useState } from 'react'

import styles from './KanbanBoard.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useDeleteIssue } from '@/api/issues'
import type { IssueListItem } from '@/api/types'
import {
  Button,
  Dialog,
  DialogContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/design-system'

/** A card's "…" menu: Delete task, for team lead and above (AFIT, 28 Oct 2026). Clicks inside it
 * (and in its menu and dialog, which React bubbles through the card) neither drag nor open the card. */
export function CardMenu({ issue }: { issue: IssueListItem }) {
  const [confirming, setConfirming] = useState(false)
  const remove = useDeleteIssue()
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation()
  if (!issue.can_delete) return null

  const close = (open: boolean) => {
    if (!open) {
      setConfirming(false)
      remove.reset()
    }
  }

  return (
    <span onClick={stop} onPointerDown={stop} onKeyDown={stop} className={styles.cardMenu}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" className={styles.cardMenuButton} aria-label={`More actions for ${issue.summary}`}>
            <MoreHorizontal size={14} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => setConfirming(true)}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--tf-danger)' }}>
              <Trash2 size={14} /> Delete task
            </span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={confirming} onOpenChange={close}>
        <DialogContent title="Delete this task?" maxWidth={460}>
          <p style={{ margin: '0 0 8px' }}>
            <strong>{issue.summary}</strong> ({issue.key}) will be deleted permanently, with its sub-tasks, comments,
            attachments, history, AI pre-check runs and coordinator follow-ups. This can&apos;t be undone.
          </p>
          <p style={{ margin: '0 0 12px', color: 'var(--tf-text-secondary)', fontSize: 13 }}>
            Hours already logged on it stay in timesheets, without the task. To keep the task&apos;s record, move it to To be
            Archived instead.
          </p>
          {remove.isError && (
            <p role="alert" style={{ margin: '0 0 12px', color: 'var(--tf-danger)', fontSize: 13 }}>
              {extractErrorMessage(remove.error, 'The task could not be deleted.')}
            </p>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button variant="secondary" onClick={() => close(false)}>Cancel</Button>
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(issue.key, { onSuccess: () => close(false) })}>
              {remove.isPending ? 'Deleting…' : 'Delete permanently'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </span>
  )
}
