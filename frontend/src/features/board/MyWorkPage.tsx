import { useMemo } from 'react'

import { CATEGORY_COLUMNS } from './categoryColumns'
import { KanbanBoard } from './KanbanBoard'
import { useIssues, useMoveIssue } from '@/api/issues'
import { useCategoryStatusMaps } from '@/api/projects'
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
      availableSwimlanes={['none', 'project']}
      emptyMessage="Nothing assigned to you yet."
      onMoveIssue={({ issue, column, beforeId, afterId }) => {
        const statusId = column.category ? maps[issue.project_key]?.[column.category] : undefined
        moveIssue.mutate({ key: issue.key, status_id: statusId, before_id: beforeId, after_id: afterId })
      }}
    />
  )
}
