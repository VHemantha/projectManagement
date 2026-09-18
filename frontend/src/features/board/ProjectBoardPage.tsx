import { useIssues, useMoveIssue } from '@/api/issues'
import { useProjectBoard } from '@/api/projects'
import { useSprints } from '@/api/sprints'
import { useProjectContext } from '@/features/projects/useProjectContext'
import { KanbanBoard } from './KanbanBoard'
import type { SwimlaneMode } from './laneUtils'

export function ProjectBoardPage() {
  const { project } = useProjectContext()
  const { data: board, isLoading: boardLoading } = useProjectBoard(project.key)
  const { data: sprints } = useSprints(project.key)
  const moveIssue = useMoveIssue()

  const activeSprint = sprints?.find((s) => s.state === 'active')
  const isScrum = project.project_type === 'scrum'

  const { data: issuesPage, isLoading: issuesLoading } = useIssues(
    {
      project: project.key,
      no_parent: true,
      exclude_type: 'Epic',
      page_size: 300,
      ordering: 'rank',
      ...(isScrum ? { sprint: activeSprint?.id } : {}),
    },
    isScrum ? !!activeSprint : true,
  )

  if (isScrum && !activeSprint) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--tf-text-subtle)' }}>
        No active sprint. Start one from the Backlog to see it here.
      </div>
    )
  }

  return (
    <KanbanBoard
      issues={issuesPage?.results ?? []}
      columns={board?.column_config ?? []}
      isLoading={boardLoading || issuesLoading}
      defaultSwimlaneMode={(board?.swimlane_mode as SwimlaneMode) ?? 'none'}
      onMoveIssue={({ issue, column, beforeId, afterId }) =>
        moveIssue.mutate({ key: issue.key, status_id: column.status_ids[0], before_id: beforeId, after_id: afterId })
      }
    />
  )
}
