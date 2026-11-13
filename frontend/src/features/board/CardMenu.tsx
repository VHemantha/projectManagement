import { MoreHorizontal, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { DeleteTaskDialog } from './DeleteTaskDialog'
import styles from './KanbanBoard.module.css'
import type { IssueListItem } from '@/api/types'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/design-system'

/** A card's "…" menu: Delete task, for team lead and above (AFIT, 28 Oct 2026), confirmed by typing
 * DELETE (13 Nov 2026). Clicks inside it (and in its menu and dialog, which React bubbles through the
 * card) neither drag nor open the card. */
export function CardMenu({ issue }: { issue: IssueListItem }) {
  const [confirming, setConfirming] = useState(false)
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation()
  if (!issue.can_delete) return null

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
      <DeleteTaskDialog issue={issue} open={confirming} onOpenChange={setConfirming} />
    </span>
  )
}
