import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical } from 'lucide-react'

import styles from './BacklogPage.module.css'
import type { IssueListItem } from '@/api/types'
import { Avatar, IssueKey, IssueTypeIcon, PriorityIcon } from '@/design-system'
import { useUiStore } from '@/store/uiStore'

export function IssueRow({ issue }: { issue: IssueListItem }) {
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: issue.id,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`${styles.row} ${isDragging ? styles.dragging : ''}`}
    >
      <span className={styles.dragHandle} {...attributes} {...listeners}>
        <GripVertical size={14} />
      </span>
      {issue.epic && (
        <span className={styles.epicStripe} style={{ background: issue.epic.epic_color }} title={issue.epic.epic_name} />
      )}
      <IssueTypeIcon typeName={issue.issue_type.name} size={14} />
      <IssueKey value={issue.key} />
      <span className={styles.rowSummary} onClick={() => openIssueModal(issue.key)}>
        {issue.summary}
      </span>
      <div className={styles.rowMeta}>
        {issue.labels.slice(0, 2).map((l) => (
          <span
            key={l.id}
            style={{ fontSize: 11, padding: '1px 6px', borderRadius: 3, background: l.color, color: '#172B4D' }}
          >
            {l.name}
          </span>
        ))}
        <PriorityIcon priority={issue.priority} size={14} />
        {issue.story_points != null && <span className={styles.points}>{issue.story_points}</span>}
        <Avatar name={issue.assignee?.display_name ?? 'Unassigned'} src={issue.assignee?.avatar} size={24} />
      </div>
    </div>
  )
}
