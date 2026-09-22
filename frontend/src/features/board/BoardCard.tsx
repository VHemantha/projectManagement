import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Calendar } from 'lucide-react'
import type { ReactNode } from 'react'

import styles from './KanbanBoard.module.css'
import { useRunningTimer } from '@/api/timesheets'
import type { CardColorRule, CardFieldKey, IssueListItem } from '@/api/types'
import { Avatar, IssueKey, IssueTypeIcon, PriorityIcon } from '@/design-system'
import { TimerButton } from '@/features/timesheets/TimerButton'
import { useUiStore } from '@/store/uiStore'

// Field-key -> render-fn lookup for the configurable meta-right row (Section 1 of the board
// customization addendum). A card_fields value with no entry here renders nothing — harmless,
// and lets the type list new keys (e.g. "current_responsible", "time_logged") ahead of the
// backend/data support landing for them, without this file needing to know about that yet.
const META_FIELD_RENDERERS: Partial<Record<CardFieldKey, (issue: IssueListItem) => ReactNode>> = {
  story_points: (issue) =>
    issue.story_points != null && (
      <span key="story_points" style={{ fontSize: 11, color: 'var(--tf-text-subtle)', fontWeight: 600 }}>
        {issue.story_points}
      </span>
    ),
  priority: (issue) => <PriorityIcon key="priority" priority={issue.priority} size={13} />,
  assignee: (issue) => (
    <Avatar
      key="assignee"
      name={issue.assignee?.display_name ?? 'Unassigned'}
      src={issue.assignee?.avatar}
      size={22}
    />
  ),
  due_date: (issue) =>
    issue.due_date && (
      <span
        key="due_date"
        title={issue.due_date}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: 11, color: 'var(--tf-text-subtle)' }}
      >
        <Calendar size={11} />
        {new Date(issue.due_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
      </span>
    ),
  labels: (issue) =>
    issue.labels.length > 0 && (
      <span key="labels" style={{ display: 'inline-flex', gap: 3 }}>
        {issue.labels.slice(0, 3).map((l) => (
          <span
            key={l.id}
            title={l.name}
            style={{ width: 8, height: 8, borderRadius: 2, background: l.color }}
          />
        ))}
      </span>
    ),
  current_responsible: (issue) =>
    issue.current_responsible && (
      <span key="current_responsible" title={`With: ${issue.current_responsible.display_name}`}>
        <Avatar name={issue.current_responsible.display_name} src={issue.current_responsible.avatar} size={18} />
      </span>
    ),
  // "linked_issue_count", "time_logged" are listed in CardFieldKey for forward-compat (board
  // settings can already offer them as checkboxes) but have no renderer yet — IssueListItem
  // doesn't carry that data. They render as a no-op via the lookup miss above until a later
  // stage adds the underlying field.
}

const DEFAULT_CARD_FIELDS: CardFieldKey[] = ['epic_tag', 'story_points', 'priority', 'assignee']

function colorForRule(issue: IssueListItem, rule: CardColorRule | undefined): string | undefined {
  switch (rule) {
    case 'priority':
      return `var(--tf-priority-${issue.priority})`
    case 'issue_type':
      return issue.issue_type.color
    case 'label':
      return issue.labels[0]?.color
    default:
      return undefined
  }
}

export function BoardCard({
  issue,
  cardFields = DEFAULT_CARD_FIELDS,
  cardColorRule,
}: {
  issue: IssueListItem
  cardFields?: CardFieldKey[]
  cardColorRule?: CardColorRule
}) {
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
  const metaFields = cardFields.filter((f) => f !== 'epic_tag')
  const accentColor = colorForRule(issue, cardColorRule)

  return (
    <div
      ref={setNodeRef}
      style={accentColor ? { ...style, borderLeft: `3px solid ${accentColor}` } : style}
      className={`${styles.card} ${isDragging ? styles.dragging : ''}`}
      onClick={() => openIssueModal(issue.key)}
      {...attributes}
      {...listeners}
    >
      <span className={styles.cardTimerBtn} style={isRunningHere ? { display: 'flex' } : undefined}>
        <TimerButton issueId={issue.id} size="sm" />
      </span>
      {cardFields.includes('epic_tag') && issue.epic && (
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
          {metaFields.map((field) => META_FIELD_RENDERERS[field]?.(issue) ?? null)}
        </div>
      </div>
    </div>
  )
}
