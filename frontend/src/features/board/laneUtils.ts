import type { IssueListItem } from '@/api/types'
import type { BoardColumn } from '@/api/types'

export type SwimlaneMode = 'none' | 'epic' | 'assignee' | 'parent' | 'project'

/** A board column can map to more than one workflow status. When a card is dropped into a
 * column, keep the issue's current status if it's already one of that column's mapped
 * statuses (e.g. dropped back into the same multi-status column) rather than forcing it onto
 * the column's first status — only reassign when the issue is actually leaving the set.
 * Returns null for a column with no mapped statuses (e.g. a misconfigured/empty column),
 * since there's no valid status to assign — callers must treat that as a no-op drop rather
 * than sending a status_id-less request that silently leaves the issue unchanged. */
export function resolveDropStatusId(issue: IssueListItem, column: BoardColumn): number | null {
  if (column.status_ids.includes(issue.status.id)) return issue.status.id
  return column.status_ids[0] ?? null
}

export interface Lane {
  id: string
  label: string | null
  color?: string
  issues: IssueListItem[]
}

export function computeLanes(issues: IssueListItem[], mode: SwimlaneMode): Lane[] {
  if (mode === 'assignee') {
    const groups = new Map<string, Lane>()
    for (const issue of issues) {
      const id = issue.assignee ? String(issue.assignee.id) : 'unassigned'
      const label = issue.assignee?.display_name ?? 'Unassigned'
      if (!groups.has(id)) groups.set(id, { id, label, issues: [] })
      groups.get(id)!.issues.push(issue)
    }
    return [...groups.values()].sort((a, b) => {
      if (a.id === 'unassigned') return 1
      if (b.id === 'unassigned') return -1
      return (a.label ?? '').localeCompare(b.label ?? '')
    })
  }

  if (mode === 'epic') {
    const groups = new Map<string, Lane>()
    for (const issue of issues) {
      const id = issue.epic ? String(issue.epic.id) : 'no-epic'
      const label = issue.epic?.epic_name ?? 'No epic'
      const color = issue.epic?.epic_color
      if (!groups.has(id)) groups.set(id, { id, label, color, issues: [] })
      groups.get(id)!.issues.push(issue)
    }
    return [...groups.values()].sort((a, b) => {
      if (a.id === 'no-epic') return 1
      if (b.id === 'no-epic') return -1
      return (a.label ?? '').localeCompare(b.label ?? '')
    })
  }

  if (mode === 'project') {
    const groups = new Map<string, Lane>()
    for (const issue of issues) {
      const id = issue.project_key
      if (!groups.has(id)) groups.set(id, { id, label: issue.project_key, issues: [] })
      groups.get(id)!.issues.push(issue)
    }
    return [...groups.values()].sort((a, b) => (a.label ?? '').localeCompare(b.label ?? ''))
  }

  // 'parent' mode: the board only ever receives top-level (non-subtask) issues,
  // so there's no parent grouping to show yet — falls back to a single lane.
  // 'none' mode is also a single lane.
  return [{ id: 'all', label: null, issues }]
}
