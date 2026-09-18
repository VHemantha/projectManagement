import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import styles from './KanbanBoard.module.css'
import { useRunningTimer } from '@/api/timesheets'
import type { IssueListItem } from '@/api/types'
import { Avatar, IssueKey, IssueTypeIcon, PriorityIcon } from '@/design-system'
import { TimerButton } from '@/features/timesheets/TimerButton'
import { useUiStore } from '@/store/uiStore'

export function BoardCard({ issue }: { issue: IssueListItem }) {
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const { data: running } = useRunningTimer()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: issue.id,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }
  const isRunningHere = running?.issue?.id === issue.id

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`${styles.card} ${isDragging ? styles.dragging : ''}`}
      onClick={() => openIssueModal(issue.key)}
      {...attributes}
      {...listeners}
    >
      <span className={styles.cardTimerBtn} style={isRunningHere ? { display: 'flex' } : undefined}>
        <TimerButton issueId={issue.id} size="sm" />
      </span>
      {issue.epic && (
        <span className={styles.cardEpicTag} style={{ background: issue.epic.epic_color }}>
          {issue.epic.epic_name}
        </span>
      )}
      <div className={styles.cardSummary}>{issue.summary}</div>
      <div className={styles.cardFooter}>
        <IssueTypeIcon typeName={issue.issue_type.name} size={13} />
        <span className={styles.cardKey}>
          <IssueKey value={issue.key} />
        </span>
        <div className={styles.cardMetaRight}>
          {issue.story_points != null && (
            <span style={{ fontSize: 11, color: 'var(--tf-text-subtle)', fontWeight: 600 }}>
              {issue.story_points}
            </span>
          )}
          <PriorityIcon priority={issue.priority} size={13} />
          <Avatar name={issue.assignee?.display_name ?? 'Unassigned'} src={issue.assignee?.avatar} size={22} />
        </div>
      </div>
    </div>
  )
}
