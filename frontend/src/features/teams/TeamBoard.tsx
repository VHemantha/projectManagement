import { useMemo } from 'react'

import { useIssues, useMoveIssue } from '@/api/issues'
import { useCategoryStatusMaps } from '@/api/projects'
import type { TeamDetail } from '@/api/types'
import { CATEGORY_COLUMNS } from '@/features/board/categoryColumns'
import { KanbanBoard } from '@/features/board/KanbanBoard'

export function TeamBoard({ team }: { team: TeamDetail }) {
  const moveIssue = useMoveIssue()
  const memberIds = useMemo(() => team.memberships.map((m) => m.user.id), [team])

  const { data: issuesPage, isLoading } = useIssues(
    {
      assignee_in: memberIds.join(','),
      no_parent: true,
      exclude_type: 'Epic',
      page_size: 300,
      ordering: 'rank',
    },
    memberIds.length > 0,
  )

  const projectKeys = useMemo(
    () => [...new Set((issuesPage?.results ?? []).map((i) => i.project_key))],
    [issuesPage],
  )
  const { maps } = useCategoryStatusMaps(projectKeys)

  return (
    <KanbanBoard
      issues={issuesPage?.results ?? []}
      columns={CATEGORY_COLUMNS}
      isLoading={isLoading}
      defaultSwimlaneMode="project"
      availableSwimlanes={['none', 'project', 'assignee']}
      emptyMessage="No issues assigned to this team's members."
      onMoveIssue={({ issue, column, beforeId, afterId }) => {
        const statusId = column.category ? maps[issue.project_key]?.[column.category] : undefined
        moveIssue.mutate({ key: issue.key, status_id: statusId, before_id: beforeId, after_id: afterId })
      }}
    />
  )
}
