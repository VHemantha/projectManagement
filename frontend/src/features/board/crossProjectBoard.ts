import { useMemo } from 'react'

import { CATEGORY_COLUMNS } from './categoryColumns'
import type { CardConfig } from './KanbanBoard'
import { resolveDropStatusId } from './laneUtils'
import { useProjectBoards } from '@/api/projects'
import type { Board, BoardColumn, IssueListItem, WorkflowStatus } from '@/api/types'

export function cardConfigOf(board: Board | undefined): CardConfig | undefined {
  if (!board) return undefined
  return {
    cardFields: board.card_fields,
    cardColorRule: board.card_color_rule,
    cardColors: board.card_colors,
    cardColorStyle: board.card_color_style,
  }
}

/** The status a card should get when dropped into a To Do / In Progress / Done column: keep
 * its status if it's already in that category (a reorder), otherwise the first status of that
 * category in the project's own column order — the same stage its project board would use. */
export function statusForCategory(
  issue: IssueListItem,
  category: WorkflowStatus['category'],
  board: Board | undefined,
): number | null {
  if (issue.status.category === category) return issue.status.id
  if (!board) return null
  const byId = new Map(board.statuses.map((s) => [s.id, s]))
  for (const column of board.column_config) {
    for (const id of column.status_ids) {
      if (byId.get(id)?.category === category) return id
    }
  }
  return board.statuses.find((s) => s.category === category)?.id ?? null
}

/** Several projects' boards as one: a column per stage name (AFIT's stages are the same on every
 * board), holding that stage's status from each project, in the first board's order; a stage
 * only some projects have is added after. Null when there is nothing shared to go on. */
export function mergeColumns(boards: (Board | undefined)[]): BoardColumn[] | null {
  if (!boards.length || boards.some((b) => !b)) return null
  const merged = new Map<string, BoardColumn>()
  for (const board of boards as Board[]) {
    for (const col of board.column_config) {
      const key = col.name.trim().toLowerCase()
      const existing = merged.get(key)
      if (existing) existing.status_ids = [...existing.status_ids, ...col.status_ids]
      else merged.set(key, { name: col.name, status_ids: [...col.status_ids], wip_limit: null, ...(col.color ? { color: col.color } : {}) })
    }
  }
  const columns = [...merged.values()]
  // Projects with nothing in common (each its own stage names): the shared categories read better.
  const shared = columns.filter((c) => (boards as Board[]).every((b) => b.column_config.some((x) => x.name.trim().toLowerCase() === c.name.trim().toLowerCase())))
  return shared.length ? columns : null
}

/** Board settings for views that aggregate issues across projects (Team, My Work, All issues),
 * so they match each project's own board:
 * - every card is drawn with its project's card fields and colour coding;
 * - one project's cards: its real columns (names, colours, WIP limits, custom stages); several
 *   projects': a column per stage they share (AFIT's eight), else the shared status categories. */
export function useCrossProjectBoard(issues: IssueListItem[]) {
  const projectKeys = useMemo(() => [...new Set(issues.map((i) => i.project_key))].sort(), [issues])
  const { boards, isLoading } = useProjectBoards(projectKeys)
  const single = projectKeys.length === 1 ? boards[projectKeys[0]] : undefined

  const cardConfigByProject = useMemo(() => {
    const out: Record<string, CardConfig> = {}
    for (const [key, board] of Object.entries(boards)) out[key] = cardConfigOf(board)!
    return out
  }, [boards])

  const merged = useMemo(() => (single ? null : mergeColumns(projectKeys.map((k) => boards[k]))), [single, projectKeys, boards])
  const columns: BoardColumn[] = single ? single.column_config : (merged ?? CATEGORY_COLUMNS)

  const resolveStatus = (issue: IssueListItem, column: BoardColumn): number | null => {
    if (column.category) return statusForCategory(issue, column.category, boards[issue.project_key])
    if (merged) {
      // The stage's status in the card's own project.
      if (column.status_ids.includes(issue.status.id)) return issue.status.id
      const own = new Set((boards[issue.project_key]?.statuses ?? []).map((s) => s.id))
      return column.status_ids.find((id) => own.has(id)) ?? null
    }
    return resolveDropStatusId(issue, column)
  }

  return {
    columns,
    cardConfigByProject,
    resolveStatus,
    // The columns depend on the projects' board settings, so wait for them.
    isLoading: projectKeys.length > 0 && isLoading,
  }
}
