import { useMemo } from 'react'

import { useCrossProjectBoard } from './crossProjectBoard'
import { defaultsFromColumn } from './createFromBoard'
import { KanbanBoard } from './KanbanBoard'
import { useIssues, useMoveIssue } from '@/api/issues'
import { CeoDashboard } from '@/features/dashboard/CeoDashboard'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'

/** Home: the tasks assigned to you; for the CEO, the organisation overview (AFIT, 28 Oct 2026). */
export function MyWorkPage() {
  const isCeo = useAuthStore((s) => s.user?.role === 'ceo')
  return isCeo ? <CeoDashboard /> : <AssignedToMe />
}

function AssignedToMe() {
  const currentUser = useAuthStore((s) => s.user)
  const moveIssue = useMoveIssue()
  const openCreateIssue = useUiStore((s) => s.openCreateIssue)

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
      emptyMessage="Nothing assigned to you yet."
      // My work: the new task is mine.
      onCreateIssue={(ctx) => openCreateIssue({ ...defaultsFromColumn(ctx), assigneeId: currentUser?.id })}
      onMoveIssue={({ issue, column, beforeId, afterId }) => {
        const statusId = board.resolveStatus(issue, column)
        if (statusId === null) return
        moveIssue.mutate({ key: issue.key, status_id: statusId, before_id: beforeId, after_id: afterId })
      }}
    />
  )
}
