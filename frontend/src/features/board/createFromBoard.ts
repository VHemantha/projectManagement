import type { CreateContext } from './KanbanBoard'
import type { CreateIssueDefaults } from '@/store/uiStore'

/** What "+" on a board column knows about the new task: the column (its status, or its category
 * on a board that spans projects) and the swimlane (its epic, assignee or project). The page adds
 * what it knows itself (project, workspace, sub-workspace). */
export function defaultsFromColumn({ column, lane, swimlaneMode }: CreateContext): CreateIssueDefaults {
  const d: CreateIssueDefaults = { columnName: column.name }
  if (column.category) d.statusCategory = column.category
  else if (column.status_ids.length) d.statusId = column.status_ids[0]
  if (swimlaneMode === 'epic' && /^\d+$/.test(lane.id)) d.epicId = Number(lane.id)
  if (swimlaneMode === 'assignee' && /^\d+$/.test(lane.id)) d.assigneeId = Number(lane.id)
  if (swimlaneMode === 'project' && lane.id !== 'all') d.projectKey = lane.id
  return d
}
