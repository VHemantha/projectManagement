import { useMemo } from 'react'

import { useIssues, useMoveIssue } from '@/api/issues'
import type { TeamDetail } from '@/api/types'
import { useCrossProjectBoard } from '@/features/board/crossProjectBoard'
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

  const issues = useMemo(() => issuesPage?.results ?? [], [issuesPage])
  const board = useCrossProjectBoard(issues)

  return (
    <KanbanBoard
      issues={issues}
      columns={board.columns}
      cardConfigByProject={board.cardConfigByProject}
      isLoading={isLoading || board.isLoading}
      defaultSwimlaneMode="project"
      availableSwimlanes={['none', 'project', 'assignee']}
      emptyMessage="No tasks assigned to this workspace's members."
      onMoveIssue={({ issue, column, beforeId, afterId }) => {
        const statusId = board.resolveStatus(issue, column)
        if (statusId === null) return
        moveIssue.mutate({ key: issue.key, status_id: statusId, before_id: beforeId, after_id: afterId })
      }}
    />
  )
}
