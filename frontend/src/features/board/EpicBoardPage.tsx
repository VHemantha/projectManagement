import { useParams } from 'react-router-dom'

import { KanbanBoard } from './KanbanBoard'
import { resolveDropStatusId } from './laneUtils'
import { useIssue, useIssues, useMoveIssue } from '@/api/issues'
import { useProjectBoard } from '@/api/projects'

export function EpicBoardPage() {
  const { epicKey } = useParams<{ key: string; epicKey: string }>()
  const { data: epic } = useIssue(epicKey)
  const { data: board, isLoading: boardLoading } = useProjectBoard(epic?.project)
  const moveIssue = useMoveIssue()

  const { data: issuesPage, isLoading: issuesLoading } = useIssues(
    { epic: epic?.id, no_parent: true, exclude_type: 'Epic', page_size: 300, ordering: 'rank' },
    !!epic,
  )

  if (!epic) return null

  return (
    <div style={{ height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 24px 0' }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: epic.epic_color }} />
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>{epic.epic_name || epic.summary} board</h1>
      </div>
      <div style={{ height: 'calc(100% - 56px)' }}>
        <KanbanBoard
          issues={issuesPage?.results ?? []}
          columns={board?.column_config ?? []}
          isLoading={boardLoading || issuesLoading}
          availableSwimlanes={['none', 'assignee']}
          emptyMessage="No issues under this epic yet."
          onMoveIssue={({ issue, column, beforeId, afterId }) =>
            moveIssue.mutate({
              key: issue.key,
              status_id: resolveDropStatusId(issue, column),
              before_id: beforeId,
              after_id: afterId,
            })
          }
        />
      </div>
    </div>
  )
}
