import { useMemo } from 'react'

import { useCrossProjectBoard } from './crossProjectBoard'
import { KanbanBoard } from './KanbanBoard'
import { useIssues, useMoveIssue } from '@/api/issues'
import { useAuthStore } from '@/store/authStore'

export function MyWorkPage() {
  const currentUser = useAuthStore((s) => s.user)
  const moveIssue = useMoveIssue()

  const { data: issuesPage, isLoading } = useIssues(
    {
      assignee: currentUser?.id,
      no_parent: true,
      exclude_type: 'Epic',
      page_size: 300,
      ordering: 'rank',
    },
    !!currentUser,
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
      availableSwimlanes={['none', 'project']}
      emptyMessage="Nothing assigned to you yet."
      onMoveIssue={({ issue, column, beforeId, afterId }) => {
        const statusId = board.resolveStatus(issue, column)
        if (statusId === null) return
        moveIssue.mutate({ key: issue.key, status_id: statusId, before_id: beforeId, after_id: afterId })
      }}
    />
  )
}
