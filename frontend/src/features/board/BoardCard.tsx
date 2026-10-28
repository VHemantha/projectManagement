import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { differenceInCalendarDays, format, parseISO } from 'date-fns'
import { Calendar } from 'lucide-react'
import type { ReactNode } from 'react'

import { CardValue } from './CardValue'
import { cardAccentColor, withAlpha } from './cardColors'
import styles from './KanbanBoard.module.css'
import { useRunningTimer } from '@/api/timesheets'
import type { CardColorRule, CardColors, CardColorStyle, CardFieldKey, IssueListItem } from '@/api/types'
import { Avatar, PriorityIcon, StatusBadge } from '@/design-system'
import { TimerButton } from '@/features/timesheets/TimerButton'
import { useUiStore } from '@/store/uiStore'

const PRIORITY_LABELS: Record<IssueListItem['priority'], string> = {
  highest: 'Highest', high: 'High', medium: 'Medium', low: 'Low', lowest: 'Lowest',
}

/** The deadline: red once past (unless the task is finished), amber within two days. */
function Deadline({ issue }: { issue: IssueListItem }) {
  if (!issue.due_date) {
    return <span className={styles.cardDeadline} style={{ color: 'var(--tf-text-subtle)' }}>No deadline</span>
  }
  const due = parseISO(issue.due_date)
  const days = differenceInCalendarDays(due, new Date())
  const finished = issue.status.category === 'done'
  const color = finished ? 'var(--tf-text-subtle)' : days < 0 ? 'var(--tf-danger)' : days <= 2 ? 'var(--tf-warning)' : 'var(--tf-text-secondary)'
  return (
    <span
      className={styles.cardDeadline}
      style={{ color, fontWeight: !finished && days < 0 ? 600 : undefined }}
      title={`Deadline ${format(due, 'EEE d MMM yyyy')}${!finished && days < 0 ? ' (overdue)' : ''}`}
    >
      <Calendar size={11} aria-hidden="true" />
      {format(due, 'd MMM')}
    </span>
  )
}

// Field-key -> render-fn lookup for the optional meta-right row (the board's card_fields). The
// deadline, stage and priority are on every card (AFIT, 28 Oct 2026); a card_fields value with no
// entry here (e.g. the old "story_points" or "time_logged") renders nothing.
const META_FIELD_RENDERERS: Partial<Record<CardFieldKey, (issue: IssueListItem) => ReactNode>> = {
  assignee: (issue) => (
    <Avatar
      key="assignee"
      name={issue.assignee?.display_name ?? 'Unassigned'}
      src={issue.assignee?.avatar}
      size={22}
    />
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
  // "linked_issue_count" is listed in CardFieldKey for forward-compat but has no renderer yet
  // (IssueListItem doesn't carry that data); it renders as a no-op via the lookup miss above.
}

const DEFAULT_CARD_FIELDS: CardFieldKey[] = ['epic_tag', 'assignee', 'job_value']

export function BoardCard({
  issue,
  cardFields = DEFAULT_CARD_FIELDS,
  cardColorRule,
  cardColors,
  cardColorStyle = 'stripe',
}: {
  issue: IssueListItem
  cardFields?: CardFieldKey[]
  cardColorRule?: CardColorRule
  cardColors?: CardColors
  cardColorStyle?: CardColorStyle
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
  const metaFields = cardFields.filter((f) => f !== 'epic_tag' && f !== 'job_value')
  const accentColor = cardAccentColor(issue, cardColorRule, cardColors)
  const tint = accentColor && cardColorStyle === 'tint' ? withAlpha(accentColor, 0.14) : undefined
  const colorStyle = accentColor
    ? {
        borderLeft: `3px solid ${accentColor}`,
        // A non-hex colour can't be made translucent; keep just the stripe then.
        ...(tint && tint !== accentColor ? { background: tint } : {}),
      }
    : {}

  return (
    <div
      ref={setNodeRef}
      style={{ ...style, ...colorStyle }}
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
      <div className={styles.cardSummary}>
        {issue.summary}
        {issue.project_name && <span className={styles.cardProject}> - {issue.project_name}</span>}
      </div>
      {cardFields.includes('job_value') && <CardValue issue={issue} />}
      <div className={styles.cardFooter}>
        <span className={styles.cardStage} title="Stage">
          <StatusBadge label={issue.status.name} category={issue.status.category} />
        </span>
        <span className={styles.cardPriority} title={`Priority: ${PRIORITY_LABELS[issue.priority]}`}>
          <PriorityIcon priority={issue.priority} size={12} />
          {PRIORITY_LABELS[issue.priority]}
        </span>
        <Deadline issue={issue} />
        <div className={styles.cardMetaRight}>
          {metaFields.map((field) => META_FIELD_RENDERERS[field]?.(issue) ?? null)}
        </div>
      </div>
    </div>
  )
}
