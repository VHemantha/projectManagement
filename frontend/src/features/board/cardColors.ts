import type { CardColorRule, CardColors, IssueListItem, Priority } from '@/api/types'
import { DUE_DATE_COLORS, PRIORITY_COLORS } from '@/lib/palette'

// Built-in colours (hex, so they can seed <input type="color">). Priority mirrors the
// --tf-priority-* tokens.
export const DEFAULT_PRIORITY_COLORS: Record<Priority, string> = { ...PRIORITY_COLORS }

export type DueDateBucket = 'overdue' | 'due_soon' | 'on_track'

export const DEFAULT_DUE_DATE_COLORS: Record<DueDateBucket, string> = { ...DUE_DATE_COLORS }

export const DUE_DATE_LABELS: Record<DueDateBucket, string> = {
  overdue: 'Overdue',
  due_soon: 'Due within 3 days',
  on_track: 'Due later',
}

const DUE_SOON_DAYS = 3

/** Open issues only: a done issue is never "overdue". Due dates are calendar dates, so compare
 * against local midnight rather than the current instant. */
export function dueDateBucket(issue: IssueListItem, today = new Date()): DueDateBucket | null {
  if (!issue.due_date || issue.status.category === 'done') return null
  const [y, m, d] = issue.due_date.split('-').map(Number)
  const due = new Date(y, m - 1, d)
  const midnight = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const days = Math.round((due.getTime() - midnight.getTime()) / 86_400_000)
  if (days < 0) return 'overdue'
  if (days <= DUE_SOON_DAYS) return 'due_soon'
  return 'on_track'
}

/** The accent colour a card gets under the board's colour rule, or undefined for none. */
export function cardAccentColor(
  issue: IssueListItem,
  rule: CardColorRule | undefined,
  colors: CardColors | undefined,
): string | undefined {
  switch (rule) {
    case 'priority':
      return colors?.priority?.[issue.priority] ?? DEFAULT_PRIORITY_COLORS[issue.priority]
    case 'issue_type':
      return colors?.issue_type?.[String(issue.issue_type.id)] ?? issue.issue_type.color
    case 'label':
      return issue.labels[0]?.color
    case 'due_date': {
      const bucket = dueDateBucket(issue)
      return bucket ? (colors?.due_date?.[bucket] ?? DEFAULT_DUE_DATE_COLORS[bucket]) : undefined
    }
    default:
      return undefined
  }
}

/** #rrggbb -> rgba() at the given alpha, for tinted card backgrounds. */
export function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex)
  if (!m) return hex
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
