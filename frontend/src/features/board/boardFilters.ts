import { dueDateBucket } from './cardColors'
import type { IssueListItem, Priority } from '@/api/types'

export const PRIORITY_ORDER: Priority[] = ['highest', 'high', 'medium', 'low', 'lowest']

export type DueFilter = 'any' | 'overdue' | 'due_soon' | 'has_date' | 'none'

export const DUE_FILTER_LABELS: Record<DueFilter, string> = {
  any: 'Any due date',
  overdue: 'Overdue',
  due_soon: 'Due soon',
  has_date: 'Has a due date',
  none: 'No due date',
}

export interface BoardFilters {
  onlyMine: boolean
  assigneeId: number | null
  priority: Priority | null
  due: DueFilter
  /** Label name, matched ignoring case (labels belong to workspaces, so names can repeat). */
  label: string | null
}

export const NO_FILTERS: BoardFilters = { onlyMine: false, assigneeId: null, priority: null, due: 'any', label: null }

export function hasActiveFilters(f: BoardFilters): boolean {
  return f.onlyMine || f.assigneeId != null || f.priority != null || f.due !== 'any' || f.label != null
}

/** The cards that pass every active filter. Columns still come from the board config, so the
 * remaining cards keep the board's column (status) order. */
export function filterIssues(
  issues: IssueListItem[],
  f: BoardFilters,
  currentUserId: number | undefined,
  today = new Date(),
): IssueListItem[] {
  const label = f.label?.toLowerCase()
  return issues.filter((issue) => {
    if (f.onlyMine && issue.assignee?.id !== currentUserId) return false
    if (f.assigneeId != null && issue.assignee?.id !== f.assigneeId) return false
    if (f.priority && issue.priority !== f.priority) return false
    if (f.due !== 'any') {
      const bucket = dueDateBucket(issue, today)
      if (f.due === 'none' && issue.due_date) return false
      if (f.due === 'has_date' && !issue.due_date) return false
      if (f.due === 'overdue' && bucket !== 'overdue') return false
      if (f.due === 'due_soon' && bucket !== 'due_soon') return false
    }
    if (label && !issue.labels.some((l) => l.name.toLowerCase() === label)) return false
    return true
  })
}

/** Label names on the board's cards, for the label filter (one entry per name). */
export function labelOptions(issues: IssueListItem[]): string[] {
  const names = new Map<string, string>()
  for (const issue of issues) for (const l of issue.labels) names.set(l.name.toLowerCase(), l.name)
  return [...names.values()].sort((a, b) => a.localeCompare(b))
}
