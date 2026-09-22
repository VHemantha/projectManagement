import { Settings } from 'lucide-react'
import { useState } from 'react'

import { BoardSettingsPanel } from './BoardSettingsPanel'
import { KanbanBoard } from './KanbanBoard'
import { resolveDropStatusId } from './laneUtils'
import type { SwimlaneMode } from './laneUtils'
import { useIssues, useMoveIssue } from '@/api/issues'
import { useProjectBoard } from '@/api/projects'
import { useSprints } from '@/api/sprints'
import { Button } from '@/design-system'
import { useProjectContext } from '@/features/projects/useProjectContext'
import { useAuthStore } from '@/store/authStore'

export function ProjectBoardPage() {
  const { project } = useProjectContext()
  const currentUser = useAuthStore((s) => s.user)
  const { data: board, isLoading: boardLoading } = useProjectBoard(project.key)
  const { data: sprints } = useSprints(project.key)
  const moveIssue = useMoveIssue()
  const [settingsOpen, setSettingsOpen] = useState(false)

  const activeSprint = sprints?.find((s) => s.state === 'active')
  const isScrum = project.project_type === 'scrum'

  const canConfigureBoard =
    !!currentUser &&
    (currentUser.is_staff ||
      project.lead?.id === currentUser.id ||
      project.memberships.some((m) => m.user.id === currentUser.id && m.role === 'admin'))

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
    <>
      <KanbanBoard
        issues={issuesPage?.results ?? []}
        columns={board?.column_config ?? []}
        isLoading={boardLoading || issuesLoading}
        defaultSwimlaneMode={(board?.swimlane_mode as SwimlaneMode) ?? 'none'}
        cardFields={board?.card_fields}
        cardColorRule={board?.card_color_rule}
        toolbarExtra={
          canConfigureBoard &&
          board && (
            <Button variant="subtle" size="sm" onClick={() => setSettingsOpen(true)}>
              <Settings size={14} /> Configure board
            </Button>
          )
        }
        onMoveIssue={({ issue, column, beforeId, afterId }) =>
          moveIssue.mutate({
            key: issue.key,
            status_id: resolveDropStatusId(issue, column),
            before_id: beforeId,
            after_id: afterId,
          })
        }
      />
      {board && (
        <BoardSettingsPanel
          board={board}
          projectKey={project.key}
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
        />
      )}
    </>
  )
}
