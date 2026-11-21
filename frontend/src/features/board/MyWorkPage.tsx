import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { useCrossProjectBoard } from './crossProjectBoard'
import { defaultsFromColumn } from './createFromBoard'
import { KanbanBoard } from './KanbanBoard'
import { useIssues, useMoveIssue } from '@/api/issues'
import { Tabs, TabsList, TabsTrigger } from '@/design-system'
import { CeoDashboard } from '@/features/dashboard/CeoDashboard'
import { DashboardHomePage } from '@/features/dashboard/DashboardHomePage'
import { EfficiencyTracker } from '@/features/dashboard/EfficiencyTracker'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'

/** Home: the tasks assigned to you; for the CEO, the organisation overview (AFIT, 28 Oct 2026). With the
 * dashboard and the efficiency tracker beside them (AFIT, 21 Nov 2026), as tabs (?view=dashboard|efficiency). */
export function MyWorkPage() {
  const isCeo = useAuthStore((s) => s.user?.role === 'ceo')
  const [params, setParams] = useSearchParams()
  const views = isCeo
    ? ([['overview', 'Overview'], ['efficiency', 'Efficiency tracker']] as const)
    : ([['tasks', 'My tasks'], ['dashboard', 'Dashboard'], ['efficiency', 'Efficiency tracker']] as const)
  const first = views[0][0]
  const view = views.some(([id]) => id === params.get('view')) ? (params.get('view') as string) : first
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ padding: '8px 16px 0' }}>
        <Tabs value={view} onValueChange={(next) => setParams(next === first ? {} : { view: next }, { replace: true })}>
          <TabsList aria-label="Home views">
            {views.map(([id, label]) => (
              <TabsTrigger key={id} value={id}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: view === 'tasks' ? undefined : 'auto' }}>
        {view === 'overview' && <CeoDashboard />}
        {view === 'tasks' && <AssignedToMe />}
        {view === 'dashboard' && <DashboardHomePage />}
        {view === 'efficiency' && (
          <div style={{ padding: 16 }}>
            <EfficiencyTracker team />
          </div>
        )}
      </div>
    </div>
  )
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
