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

/** Board settings for views that aggregate issues across projects (Team, My Work, All issues),
 * so they match each project's own board:
 * - every card is drawn with its project's card fields and colour coding;
 * - when all cards come from one project, its real columns (names, colours, WIP limits,
 *   custom stages) are used; with several projects, columns are the shared status categories. */
export function useCrossProjectBoard(issues: IssueListItem[]) {
  const projectKeys = useMemo(() => [...new Set(issues.map((i) => i.project_key))].sort(), [issues])
  const { boards, isLoading } = useProjectBoards(projectKeys)
  const single = projectKeys.length === 1 ? boards[projectKeys[0]] : undefined

  const cardConfigByProject = useMemo(() => {
    const out: Record<string, CardConfig> = {}
    for (const [key, board] of Object.entries(boards)) out[key] = cardConfigOf(board)!
    return out
  }, [boards])

  const columns: BoardColumn[] = single ? single.column_config : CATEGORY_COLUMNS

  const resolveStatus = (issue: IssueListItem, column: BoardColumn): number | null =>
    column.category
      ? statusForCategory(issue, column.category, boards[issue.project_key])
      : resolveDropStatusId(issue, column)

  return {
    columns,
    cardConfigByProject,
    resolveStatus,
    // Only a single-project board waits for its settings (its columns depend on them). Mixed
    // boards show category columns straight away and colour the cards as settings arrive.
    isLoading: projectKeys.length === 1 && isLoading,
  }
}
