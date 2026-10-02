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
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import styles from './KanbanBoard.module.css'
import { BoardCard } from './BoardCard'
import {
  type BoardFilters,
  DUE_FILTER_LABELS,
  type DueFilter,
  filterIssues,
  hasActiveFilters,
  labelOptions,
  NO_FILTERS,
  PRIORITY_ORDER,
} from './boardFilters'
import { type Lane, type SwimlaneMode, computeLanes } from './laneUtils'
import type {
  BoardColumn,
  CardColorRule,
  CardColors,
  CardColorStyle,
  CardFieldKey,
  IssueListItem,
  Priority,
} from '@/api/types'
import { Avatar, InlineEdit, Skeleton } from '@/design-system'
import { sentenceCase } from '@/lib/text'
import { useAuthStore } from '@/store/authStore'

/** How a card is drawn: which fields it shows and how it's colour-coded (a board's settings). */
export interface CardConfig {
  cardFields?: CardFieldKey[]
  cardColorRule?: CardColorRule
  cardColors?: CardColors
  cardColorStyle?: CardColorStyle
}

type ConfigFor = (issue: IssueListItem) => CardConfig

interface KanbanBoardProps {
  issues: IssueListItem[]
  columns: BoardColumn[]
  isLoading?: boolean
  defaultSwimlaneMode?: SwimlaneMode
  showSwimlanePicker?: boolean
  availableSwimlanes?: SwimlaneMode[]
  /** When set, column names can be renamed in place (double-click); index is the column's
   * position in `columns`. */
  onRenameColumn?: (index: number, name: string) => Promise<unknown>
  /** Extra toolbar content rendered at the end of the filters bar — e.g. a "Configure board"
   * button. Kept as an injected node rather than a boards-API-aware prop so this component
   * stays generic across all four board scopes (project, epic, team, my-work). */
  toolbarExtra?: ReactNode
  cardFields?: CardFieldKey[]
  cardColorRule?: CardColorRule
  cardColors?: CardColors
  cardColorStyle?: CardColorStyle
  /** Boards that mix projects (Team, My Work, All issues) draw each card with its own project's
   * board settings, so a card looks the same wherever it appears. Falls back to the props above. */
  cardConfigByProject?: Record<string, CardConfig>
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
  project: 'Swimlanes: Workspace',
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
  cardColors,
  cardColorStyle,
  cardConfigByProject,
  onMoveIssue,
  onRenameColumn,
  emptyMessage = 'No jobs to show.',
}: KanbanBoardProps) {
  const currentUser = useAuthStore((s) => s.user)
  const [swimlaneMode, setSwimlaneMode] = useState<SwimlaneMode>(defaultSwimlaneMode)
  const [filters, setFilters] = useState<BoardFilters>(NO_FILTERS)
  const setFilter = <K extends keyof BoardFilters>(key: K, value: BoardFilters[K]) =>
    setFilters((prev) => ({ ...prev, [key]: value }))
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [sections, setSections] = useState<Record<string, number[]>>({})
  const [issuesById, setIssuesById] = useState<Record<number, IssueListItem>>({})
  const [activeId, setActiveId] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const configFor = useCallback<ConfigFor>(
    (issue) => cardConfigByProject?.[issue.project_key] ?? { cardFields, cardColorRule, cardColors, cardColorStyle },
    [cardConfigByProject, cardFields, cardColorRule, cardColors, cardColorStyle],
  )

  // Board settings can now persist a swimlane_mode server-side; when that saved default
  // changes (e.g. after editing it in Configure Board), adopt it as the new baseline. The
  // picker below still lets a viewer locally override it for their own session without
  // writing anything back.
  useEffect(() => {
    setSwimlaneMode(defaultSwimlaneMode)
  }, [defaultSwimlaneMode])

  const filteredIssues = useMemo(
    () => filterIssues(issues, filters, currentUser?.id),
    [issues, filters, currentUser],
  )
  const labels = useMemo(() => labelOptions(issues), [issues])

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

    // Compute the drop from the current sections (already updated by dragOver), then report
    // the move once — outside the state updater, which React may call twice.
    const items = [...(sections[container] ?? [])]
    const oldIndex = items.indexOf(active.id as number)
    if (oldIndex === -1) return
    const overIndex = items.indexOf(over.id as number)
    const newIndex = overIndex >= 0 ? overIndex : items.length - 1
    items.splice(oldIndex, 1)
    items.splice(newIndex, 0, active.id as number)
    setSections((prev) => ({ ...prev, [container]: items }))

    const finalIndex = items.indexOf(active.id as number)
    const beforeId = finalIndex > 0 ? items[finalIndex - 1] : null
    const afterId = finalIndex < items.length - 1 ? items[finalIndex + 1] : null
    const issue = issuesById[active.id as number]
    const [, columnIndexStr] = container.split('::')
    const column = columns[Number(columnIndexStr)]
    if (issue && column) {
      onMoveIssue({ issue, column, beforeId, afterId })
    }
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
            background: filters.onlyMine ? 'var(--tf-blue-subtle)' : undefined,
            color: filters.onlyMine ? 'var(--tf-blue)' : undefined,
          }}
          aria-pressed={filters.onlyMine}
          onClick={() => setFilter('onlyMine', !filters.onlyMine)}
        >
          Only my jobs
        </button>
        <div className={styles.avatarStack}>
          {assignees.map(
            (a) =>
              a && (
                <span
                  key={a.id}
                  className={filters.assigneeId === a.id ? styles.avatarActive : ''}
                  onClick={() => setFilter('assigneeId', filters.assigneeId === a.id ? null : a.id)}
                >
                  <Avatar name={a.display_name} src={a.avatar} size={28} />
                </span>
              ),
          )}
        </div>
        <select
          className={styles.select}
          aria-label="Filter by priority"
          value={filters.priority ?? ''}
          onChange={(e) => setFilter('priority', (e.target.value || null) as Priority | null)}
        >
          <option value="">Any priority</option>
          {PRIORITY_ORDER.map((p) => (
            <option key={p} value={p}>
              {sentenceCase(p)}
            </option>
          ))}
        </select>
        <select
          className={styles.select}
          aria-label="Filter by due date"
          value={filters.due}
          onChange={(e) => setFilter('due', e.target.value as DueFilter)}
        >
          {(Object.keys(DUE_FILTER_LABELS) as DueFilter[]).map((d) => (
            <option key={d} value={d}>
              {DUE_FILTER_LABELS[d]}
            </option>
          ))}
        </select>
        {labels.length > 0 && (
          <select
            className={styles.select}
            aria-label="Filter by label"
            value={filters.label ?? ''}
            onChange={(e) => setFilter('label', e.target.value || null)}
          >
            <option value="">Any label</option>
            {labels.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        )}
        {hasActiveFilters(filters) && (
          <button type="button" className={styles.clearFilters} onClick={() => setFilters(NO_FILTERS)}>
            Clear filters
          </button>
        )}
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
              configFor={configFor}
              onRenameColumn={onRenameColumn}
            />
          ))}
          <DragOverlay>
            {activeIssue ? (
              <BoardCard issue={activeIssue} {...configFor(activeIssue)} />
            ) : null}
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
  configFor,
  onRenameColumn,
}: {
  lane: Lane
  columns: BoardColumn[]
  sections: Record<string, number[]>
  collapsed: Set<number>
  setCollapsed: (fn: (prev: Set<number>) => Set<number>) => void
  issuesById: Record<number, IssueListItem>
  configFor: ConfigFor
  onRenameColumn?: (index: number, name: string) => Promise<unknown>
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
              color={col.color}
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
              configFor={configFor}
              onRename={onRenameColumn && ((name) => onRenameColumn(colIndex, name))}
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
  color,
  count,
  wipLimit,
  overLimit,
  collapsed,
  onToggleCollapse,
  issueIds,
  issuesById,
  configFor,
  onRename,
}: {
  containerId: string
  title: string
  color?: string | null
  count: number
  wipLimit: number | null
  overLimit: boolean
  collapsed: boolean
  onToggleCollapse: () => void
  issueIds: number[]
  issuesById: Record<number, IssueListItem>
  configFor: ConfigFor
  onRename?: (name: string) => Promise<unknown>
}) {
  const { setNodeRef } = useDroppable({ id: containerId })

  return (
    <div className={`${styles.column} ${collapsed ? styles.collapsed : ''}`}>
      <div
        className={styles.columnHeader}
        style={color ? { boxShadow: `inset 0 3px 0 ${color}` } : undefined}
        onClick={onToggleCollapse}
      >
        {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
        {!collapsed && (
          <>
            {color && <span className={styles.columnDot} style={{ background: color }} />}
            {onRename ? (
              // Clicking the name doesn't collapse the column; double-clicking renames it.
              <span className={styles.columnTitle} onClick={(e) => e.stopPropagation()}>
                <InlineEdit value={title} label="Column name" maxLength={50} activation="doubleClick" onSave={onRename} />
              </span>
            ) : (
              <span>{title}</span>
            )}
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
                    <BoardCard key={id} issue={issuesById[id]} {...configFor(issuesById[id])} />
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
