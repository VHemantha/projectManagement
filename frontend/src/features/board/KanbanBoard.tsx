import {
  DndContext,
  type DragEndEvent,
  type DragOverEvent,
  DragOverlay,
  type DragStartEvent,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { type ReactNode, useEffect, useMemo, useState } from 'react'

import styles from './KanbanBoard.module.css'
import { BoardCard } from './BoardCard'
import { type Lane, type SwimlaneMode, computeLanes } from './laneUtils'
import type { BoardColumn, CardColorRule, CardFieldKey, IssueListItem } from '@/api/types'
import { Avatar, Skeleton } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

interface KanbanBoardProps {
  issues: IssueListItem[]
  columns: BoardColumn[]
  isLoading?: boolean
  defaultSwimlaneMode?: SwimlaneMode
  showSwimlanePicker?: boolean
  availableSwimlanes?: SwimlaneMode[]
  /** Extra toolbar content rendered at the end of the filters bar — e.g. a "Configure board"
   * button. Kept as an injected node rather than a boards-API-aware prop so this component
   * stays generic across all four board scopes (project, epic, team, my-work). */
  toolbarExtra?: ReactNode
  cardFields?: CardFieldKey[]
  cardColorRule?: CardColorRule
  onMoveIssue: (params: {
    issue: IssueListItem
    column: BoardColumn
    beforeId: number | null
    afterId: number | null
  }) => void
  emptyMessage?: string
}

const SWIMLANE_LABELS: Record<SwimlaneMode, string> = {
  none: 'No swimlanes',
  epic: 'Swimlanes: Epic',
  assignee: 'Swimlanes: Assignee',
  project: 'Swimlanes: Project',
  parent: 'Swimlanes: Parent',
}

function containerKey(laneId: string, columnIndex: number) {
  return `${laneId}::${columnIndex}`
}

export function KanbanBoard({
  issues,
  columns,
  isLoading,
  defaultSwimlaneMode = 'none',
  showSwimlanePicker = true,
  availableSwimlanes = ['none', 'epic', 'assignee'],
  toolbarExtra,
  cardFields,
  cardColorRule,
  onMoveIssue,
  emptyMessage = 'No issues to show.',
}: KanbanBoardProps) {
  const currentUser = useAuthStore((s) => s.user)
  const [swimlaneMode, setSwimlaneMode] = useState<SwimlaneMode>(defaultSwimlaneMode)
  const [onlyMine, setOnlyMine] = useState(false)
  const [assigneeFilter, setAssigneeFilter] = useState<number | null>(null)
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [sections, setSections] = useState<Record<string, number[]>>({})
  const [issuesById, setIssuesById] = useState<Record<number, IssueListItem>>({})
  const [activeId, setActiveId] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  // Board settings can now persist a swimlane_mode server-side; when that saved default
  // changes (e.g. after editing it in Configure Board), adopt it as the new baseline. The
  // picker below still lets a viewer locally override it for their own session without
  // writing anything back.
  useEffect(() => {
    setSwimlaneMode(defaultSwimlaneMode)
  }, [defaultSwimlaneMode])

  const filteredIssues = useMemo(() => {
    return issues.filter((issue) => {
      if (onlyMine && issue.assignee?.id !== currentUser?.id) return false
      if (assigneeFilter != null && issue.assignee?.id !== assigneeFilter) return false
      return true
    })
  }, [issues, onlyMine, assigneeFilter, currentUser])

  const lanes = useMemo(() => computeLanes(filteredIssues, swimlaneMode), [filteredIssues, swimlaneMode])

  const assignees = useMemo(() => {
    const map = new Map<number, IssueListItem['assignee']>()
    for (const issue of issues) {
      if (issue.assignee) map.set(issue.assignee.id, issue.assignee)
    }
    return [...map.values()]
  }, [issues])

  useEffect(() => {
    if (dragging) return
    const byId: Record<number, IssueListItem> = {}
    const grouped: Record<string, number[]> = {}
    for (const lane of lanes) {
      columns.forEach((col, colIndex) => {
        const key = containerKey(lane.id, colIndex)
        grouped[key] = lane.issues
          .filter((issue) =>
            col.category ? issue.status.category === col.category : col.status_ids.includes(issue.status.id),
          )
          .map((issue) => {
            byId[issue.id] = issue
            return issue.id
          })
      })
    }
    setIssuesById(byId)
    setSections(grouped)
  }, [lanes, columns, dragging])

  function findContainer(id: number | string): string | undefined {
    if (typeof id === 'string' && sections[id]) return id
    return Object.keys(sections).find((key) => sections[key].includes(id as number))
  }

  const handleDragStart = (event: DragStartEvent) => {
    setDragging(true)
    setActiveId(event.active.id as number)
  }

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event
    if (!over) return
    const activeContainer = findContainer(active.id as number)
    const overContainer = findContainer(over.id as number | string)
    if (!activeContainer || !overContainer || activeContainer === overContainer) return

    setSections((prev) => {
      const activeItems = prev[activeContainer].filter((id) => id !== active.id)
      const overItems = [...prev[overContainer]]
      const overIndex = overItems.indexOf(over.id as number)
      const insertAt = overIndex >= 0 ? overIndex : overItems.length
      overItems.splice(insertAt, 0, active.id as number)
      return { ...prev, [activeContainer]: activeItems, [overContainer]: overItems }
    })
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setDragging(false)
    setActiveId(null)
    if (!over) return
    const container = findContainer(active.id as number)
    if (!container) return

    setSections((prev) => {
      const items = [...prev[container]]
      const oldIndex = items.indexOf(active.id as number)
      if (oldIndex === -1) return prev
      const overIndex = items.indexOf(over.id as number)
      const newIndex = overIndex >= 0 ? overIndex : items.length - 1
      items.splice(oldIndex, 1)
      items.splice(newIndex, 0, active.id as number)

      const finalIndex = items.indexOf(active.id as number)
      const beforeId = finalIndex > 0 ? items[finalIndex - 1] : null
      const afterId = finalIndex < items.length - 1 ? items[finalIndex + 1] : null
      const issue = issuesById[active.id as number]
      const [, columnIndexStr] = container.split('::')
      const column = columns[Number(columnIndexStr)]

      if (issue && column) {
        onMoveIssue({ issue, column, beforeId, afterId })
      }
      return { ...prev, [container]: items }
    })
  }

  const activeIssue = activeId ? issuesById[activeId] : null

  if (isLoading) {
    return <BoardSkeleton />
  }

  if (issues.length === 0) {
    return <div className={styles.emptyBoard}>{emptyMessage}</div>
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.filtersBar}>
        <button
          className={styles.select}
          style={{
            background: onlyMine ? 'var(--tf-blue-subtle)' : undefined,
            color: onlyMine ? 'var(--tf-blue)' : undefined,
          }}
          onClick={() => setOnlyMine((v) => !v)}
        >
          Only My Issues
        </button>
        <div className={styles.avatarStack}>
          {assignees.map(
            (a) =>
              a && (
                <span
                  key={a.id}
                  className={assigneeFilter === a.id ? styles.avatarActive : ''}
                  onClick={() => setAssigneeFilter((prev) => (prev === a.id ? null : a.id))}
                >
                  <Avatar name={a.display_name} src={a.avatar} size={28} />
                </span>
              ),
          )}
        </div>
        {showSwimlanePicker && (
          <select
            className={styles.select}
            style={{ marginLeft: 'auto' }}
            value={swimlaneMode}
            onChange={(e) => setSwimlaneMode(e.target.value as SwimlaneMode)}
          >
            {availableSwimlanes.map((mode) => (
              <option key={mode} value={mode}>
                {SWIMLANE_LABELS[mode]}
              </option>
            ))}
          </select>
        )}
        {toolbarExtra}
      </div>

      <div className={styles.scrollArea}>
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
        >
          {lanes.map((lane) => (
            <BoardLane
              key={lane.id}
              lane={lane}
              columns={columns}
              sections={sections}
              collapsed={collapsed}
              setCollapsed={setCollapsed}
              issuesById={issuesById}
              cardFields={cardFields}
              cardColorRule={cardColorRule}
            />
          ))}
          <DragOverlay>
            {activeIssue ? <BoardCard issue={activeIssue} cardFields={cardFields} cardColorRule={cardColorRule} /> : null}
          </DragOverlay>
        </DndContext>
      </div>
    </div>
  )
}

function BoardLane({
  lane,
  columns,
  sections,
  collapsed,
  setCollapsed,
  issuesById,
  cardFields,
  cardColorRule,
}: {
  lane: Lane
  columns: BoardColumn[]
  sections: Record<string, number[]>
  collapsed: Set<number>
  setCollapsed: (fn: (prev: Set<number>) => Set<number>) => void
  issuesById: Record<number, IssueListItem>
  cardFields?: CardFieldKey[]
  cardColorRule?: CardColorRule
}) {
  return (
    <div className={styles.lane}>
      {lane.label && (
        <div className={styles.laneHeader}>
          {lane.color && <span className={styles.laneDot} style={{ background: lane.color }} />}
          {lane.label} ({lane.issues.length})
        </div>
      )}
      <div className={styles.columns}>
        {columns.map((col, colIndex) => {
          const key = containerKey(lane.id, colIndex)
          const ids = sections[key] ?? []
          const isCollapsed = collapsed.has(colIndex)
          const overLimit = col.wip_limit != null && ids.length > col.wip_limit
          return (
            <BoardColumnView
              key={key}
              containerId={key}
              title={col.name}
              count={ids.length}
              wipLimit={col.wip_limit}
              overLimit={overLimit}
              collapsed={isCollapsed}
              onToggleCollapse={() =>
                setCollapsed((prev) => {
                  const next = new Set(prev)
                  if (next.has(colIndex)) next.delete(colIndex)
                  else next.add(colIndex)
                  return next
                })
              }
              issueIds={ids}
              issuesById={issuesById}
              cardFields={cardFields}
              cardColorRule={cardColorRule}
            />
          )
        })}
      </div>
    </div>
  )
}

function BoardColumnView({
  containerId,
  title,
  count,
  wipLimit,
  overLimit,
  collapsed,
  onToggleCollapse,
  issueIds,
  issuesById,
  cardFields,
  cardColorRule,
}: {
  containerId: string
  title: string
  count: number
  wipLimit: number | null
  overLimit: boolean
  collapsed: boolean
  onToggleCollapse: () => void
  issueIds: number[]
  issuesById: Record<number, IssueListItem>
  cardFields?: CardFieldKey[]
  cardColorRule?: CardColorRule
}) {
  const { setNodeRef } = useDroppable({ id: containerId })

  return (
    <div className={`${styles.column} ${collapsed ? styles.collapsed : ''}`}>
      <div className={styles.columnHeader} onClick={onToggleCollapse}>
        {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
        {!collapsed && (
          <>
            <span>{title}</span>
            <span className={`${styles.columnCount} ${overLimit ? styles.overLimit : ''}`}>
              {count}
              {wipLimit != null ? ` / ${wipLimit}` : ''}
            </span>
          </>
        )}
      </div>
      {!collapsed && (
        <SortableContext items={issueIds} strategy={verticalListSortingStrategy}>
          <div ref={setNodeRef} className={styles.columnBody}>
            {issueIds.length === 0 ? (
              <div className={styles.emptyColumn}>—</div>
            ) : (
              issueIds.map(
                (id) =>
                  issuesById[id] && (
                    <BoardCard
                      key={id}
                      issue={issuesById[id]}
                      cardFields={cardFields}
                      cardColorRule={cardColorRule}
                    />
                  ),
              )
            )}
          </div>
        </SortableContext>
      )}
    </div>
  )
}

function BoardSkeleton() {
  return (
    <div className={styles.wrap}>
      <div className={styles.scrollArea}>
        <div className={styles.columns}>
          {[0, 1, 2, 3].map((col) => (
            <div className={styles.column} key={col}>
              <div className={styles.columnHeader}>
                <Skeleton width={80} height={11} />
              </div>
              <div className={styles.columnBody}>
                {[0, 1, 2].map((card) => (
                  <div className={styles.card} key={card} style={{ cursor: 'default' }}>
                    <Skeleton height={12} style={{ marginBottom: 8 }} />
                    <Skeleton width="60%" height={10} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
