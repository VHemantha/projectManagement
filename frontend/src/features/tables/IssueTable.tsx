import { type Row, createColumnHelper, useTable } from '@tanstack/react-table'
import { format } from 'date-fns'
import { Archive, ArchiveRestore, ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import { Fragment, useMemo, useState } from 'react'

import { ColumnsMenu } from './ColumnsMenu'
import styles from './IssueTable.module.css'
import { useBulkArchive, usePatchIssueField } from '@/api/issues'
import { useRunningTimer } from '@/api/timesheets'
import type { IssueListItem, Priority, WorkflowStatus } from '@/api/types'
import { useUsers } from '@/api/users'
import {
  Avatar,
  IssueKey,
  IssueTypeIcon,
  PriorityIcon,
  Skeleton,
  StatusBadge,
} from '@/design-system'
import type { StatusCategory } from '@/design-system'
import { TimerButton } from '@/features/timesheets/TimerButton'
import { moveInOrder } from '@/lib/columnOrder'
import { issueTableFeatures } from '@/lib/tableFeatures'
import { useTableLayout } from '@/lib/useTableLayout'
import { useUiStore } from '@/store/uiStore'
import { CATEGORY_LABELS } from '@/lib/text'

function TimerCell({ issueId }: { issueId: number }) {
  const { data: running } = useRunningTimer()
  const isRunningHere = running?.issue?.id === issueId
  return (
    <span className={`${styles.timerCell} ${isRunningHere ? styles.alwaysVisible : ''}`}>
      <TimerButton issueId={issueId} size="sm" />
    </span>
  )
}

export type GroupByOption = 'none' | 'status' | 'assignee' | 'project' | 'reviewer' | 'current_responsible'

const PRIORITIES: Priority[] = ['highest', 'high', 'medium', 'low', 'lowest']

const helper = createColumnHelper<typeof issueTableFeatures, IssueListItem>()

interface IssueTableProps {
  /** Saves each user's layout (columns, order, widths, sort) for this table. */
  tableId: string
  issues: IssueListItem[]
  /** Adds row checkboxes with bulk Archive / Restore. */
  selectable?: boolean
  isLoading?: boolean
  groupBy?: GroupByOption
  availableGroupBy?: GroupByOption[]
  onGroupByChange?: (g: GroupByOption) => void
  showProjectColumn?: boolean
  projectStatuses?: WorkflowStatus[]
  emptyMessage?: string
}

function StatusCell({ issue, projectStatuses }: { issue: IssueListItem; projectStatuses?: WorkflowStatus[] }) {
  const patch = usePatchIssueField()
  if (!projectStatuses) {
    return <StatusBadge label={issue.status.name} category={issue.status.category as StatusCategory} />
  }
  return (
    <select
      className={styles.inlineSelect}
      value={issue.status.id}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => patch.mutate({ key: issue.key, patch: { status_id: Number(e.target.value) } })}
    >
      {projectStatuses.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  )
}

function AssigneeCell({ issue }: { issue: IssueListItem }) {
  const patch = usePatchIssueField()
  const { data: users } = useUsers()
  return (
    <div className={styles.assigneeCell}>
      <Avatar name={issue.assignee?.display_name ?? 'Unassigned'} src={issue.assignee?.avatar} size={22} />
      <select
        className={styles.inlineSelect}
        value={issue.assignee?.id ?? ''}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) =>
          patch.mutate({
            key: issue.key,
            patch: { assignee_id: e.target.value ? Number(e.target.value) : null },
          })
        }
      >
        <option value="">Unassigned</option>
        {users?.map((u) => (
          <option key={u.id} value={u.id}>
            {u.display_name}
          </option>
        ))}
      </select>
    </div>
  )
}

type RoleField = 'preparer' | 'reviewer' | 'current_responsible'

/** Same avatar + <select> pattern as AssigneeCell, parametrized by which role field it edits
 * — Preparer/Reviewer/Current Responsible share this instead of three more near-copies. */
function RoleCell({ issue, field, patchKey }: { issue: IssueListItem; field: RoleField; patchKey: string }) {
  const patch = usePatchIssueField()
  const { data: users } = useUsers()
  const user = issue[field]
  return (
    <div className={styles.assigneeCell}>
      <Avatar name={user?.display_name ?? 'Unset'} src={user?.avatar} size={22} />
      <select
        className={styles.inlineSelect}
        value={user?.id ?? ''}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) =>
          patch.mutate({
            key: issue.key,
            patch: { [patchKey]: e.target.value ? Number(e.target.value) : null },
          })
        }
      >
        <option value="">Unset</option>
        {users?.map((u) => (
          <option key={u.id} value={u.id}>
            {u.display_name}
          </option>
        ))}
      </select>
    </div>
  )
}

function PriorityCell({ issue }: { issue: IssueListItem }) {
  const patch = usePatchIssueField()
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <PriorityIcon priority={issue.priority} size={14} />
      <select
        className={styles.inlineSelect}
        value={issue.priority}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => patch.mutate({ key: issue.key, patch: { priority: e.target.value } })}
      >
        {PRIORITIES.map((p) => (
          <option key={p} value={p}>
            {p[0].toUpperCase() + p.slice(1)}
          </option>
        ))}
      </select>
    </div>
  )
}

// Columns hidden until the user adds them from the Columns menu.
const DEFAULT_HIDDEN = ['preparer', 'reviewer', 'current_responsible', 'budgeted', 'actual', 'variance']
// Unlabelled utility columns: not listed in the Columns menu.
const UTILITY_COLUMNS = ['select', 'type', 'timer']

const hoursText = (value: number | null) => (value == null ? '—' : `${Number(value.toFixed(1))}h`)

function buildColumns(
  showProjectColumn: boolean,
  projectStatuses: WorkflowStatus[] | undefined,
  selection?: { selected: Set<string>; toggle: (key: string) => void; toggleAll: () => void; allSelected: boolean },
) {
  const cols = [
    ...(selection
      ? [
          helper.display({
            id: 'select',
            header: () => (
              <input
                type="checkbox"
                aria-label="Select all jobs"
                checked={selection.allSelected}
                onChange={selection.toggleAll}
                onClick={(e) => e.stopPropagation()}
              />
            ),
            size: 34,
            cell: (ctx) => (
              <input
                type="checkbox"
                aria-label={`Select ${ctx.row.original.key}`}
                checked={selection.selected.has(ctx.row.original.key)}
                onChange={() => selection.toggle(ctx.row.original.key)}
                onClick={(e) => e.stopPropagation()}
              />
            ),
          }),
        ]
      : []),
    helper.display({
      id: 'type',
      header: '',
      size: 36,
      cell: (ctx) => <IssueTypeIcon typeName={ctx.row.original.issue_type.name} size={14} />,
    }),
    helper.accessor('key', {
      header: 'Key',
      // Keys are full words now ("Pochin-12"), so leave room for them.
      size: 130,
      sortFn: 'alphanumeric',
      cell: (ctx) => <IssueKey value={ctx.getValue()} />,
    }),
    helper.display({
      id: 'timer',
      header: '',
      size: 32,
      cell: (ctx) => <TimerCell issueId={ctx.row.original.id} />,
    }),
    helper.accessor('summary', {
      header: 'Summary',
      size: 320,
      sortFn: 'alphanumeric',
      cell: (ctx) => {
        const openIssueModal = useUiStore.getState().openIssueModal
        return (
          <span className={styles.summaryLink} onClick={() => openIssueModal(ctx.row.original.key)}>
            {ctx.row.original.is_archived && <span className={styles.archivedBadge}>Archived</span>}
            {ctx.getValue()}
          </span>
        )
      },
    }),
    ...(showProjectColumn
      ? [
          helper.accessor('project_key', {
            header: 'Workspace',
            size: 90,
            sortFn: 'alphanumeric',
          }),
        ]
      : []),
    helper.accessor((row) => row.status.name, {
      id: 'status',
      header: 'Status',
      size: 140,
      sortFn: 'alphanumeric',
      cell: (ctx) => <StatusCell issue={ctx.row.original} projectStatuses={projectStatuses} />,
    }),
    helper.accessor((row) => row.assignee?.display_name ?? '', {
      id: 'assignee',
      header: 'Assignee',
      size: 170,
      sortFn: 'alphanumeric',
      cell: (ctx) => <AssigneeCell issue={ctx.row.original} />,
    }),
    helper.accessor((row) => row.preparer?.display_name ?? '', {
      id: 'preparer',
      header: 'Preparer',
      size: 170,
      sortFn: 'alphanumeric',
      cell: (ctx) => <RoleCell issue={ctx.row.original} field="preparer" patchKey="preparer_id" />,
    }),
    helper.accessor((row) => row.reviewer?.display_name ?? '', {
      id: 'reviewer',
      header: 'Reviewer',
      size: 170,
      sortFn: 'alphanumeric',
      cell: (ctx) => <RoleCell issue={ctx.row.original} field="reviewer" patchKey="reviewer_id" />,
    }),
    helper.accessor((row) => row.current_responsible?.display_name ?? '', {
      id: 'current_responsible',
      header: 'Current responsible',
      size: 180,
      sortFn: 'alphanumeric',
      cell: (ctx) => <RoleCell issue={ctx.row.original} field="current_responsible" patchKey="current_responsible_id" />,
    }),
    helper.accessor('priority', {
      header: 'Priority',
      size: 130,
      sortFn: 'alphanumeric',
      cell: (ctx) => <PriorityCell issue={ctx.row.original} />,
    }),
    helper.accessor('story_points', {
      header: 'Points',
      size: 70,
      sortFn: 'alphanumeric',
      cell: (ctx) => ctx.getValue() ?? '—',
    }),
    helper.accessor('due_date', {
      header: 'Due',
      size: 100,
      sortFn: 'alphanumeric',
      cell: (ctx) => (ctx.getValue() ? format(new Date(ctx.getValue() as string), 'MMM d') : '—'),
    }),
    // Actual time comes from timesheets; compare it with the job's budget.
    helper.accessor((row) => row.budgeted_hours ?? undefined, {
      id: 'budgeted',
      header: 'Budget',
      size: 90,
      sortFn: 'alphanumeric',
      sortUndefined: 'last',
      cell: (ctx) => hoursText(ctx.row.original.budgeted_hours),
    }),
    helper.accessor((row) => row.actual_hours, {
      id: 'actual',
      header: 'Actual',
      size: 90,
      sortFn: 'alphanumeric',
      cell: (ctx) => hoursText(ctx.row.original.actual_hours),
    }),
    helper.accessor((row) => (row.budgeted_hours == null ? undefined : row.budgeted_hours - row.actual_hours), {
      id: 'variance',
      header: 'Remaining',
      size: 110,
      sortFn: 'alphanumeric',
      sortUndefined: 'last',
      cell: (ctx) => {
        const { budgeted_hours: budget, actual_hours: actual } = ctx.row.original
        if (budget == null) return '—'
        const left = budget - actual
        return left < 0 ? (
          <span className={styles.overBudget}>{hoursText(-left)} over</span>
        ) : (
          <span>{hoursText(left)} left</span>
        )
      },
    }),
  ]
  return helper.columns(cols)
}

interface GroupBucket {
  key: string
  label: string
  rows: Row<typeof issueTableFeatures, IssueListItem>[]
}

function groupRows(rows: Row<typeof issueTableFeatures, IssueListItem>[], groupBy: GroupByOption): GroupBucket[] {
  if (groupBy === 'none') return [{ key: 'all', label: '', rows }]

  const buckets = new Map<string, GroupBucket>()
  for (const row of rows) {
    const issue = row.original
    let key: string
    let label: string
    if (groupBy === 'status') {
      key = String(issue.status.id)
      label = issue.status.name
    } else if (groupBy === 'assignee') {
      key = issue.assignee ? String(issue.assignee.id) : 'unassigned'
      label = issue.assignee?.display_name ?? 'Unassigned'
    } else if (groupBy === 'reviewer') {
      key = issue.reviewer ? String(issue.reviewer.id) : 'unassigned'
      label = issue.reviewer?.display_name ?? 'Unassigned'
    } else if (groupBy === 'current_responsible') {
      key = issue.current_responsible ? String(issue.current_responsible.id) : 'unassigned'
      label = issue.current_responsible?.display_name ?? 'Unassigned'
    } else {
      key = issue.project_key
      label = issue.project_key
    }
    if (!buckets.has(key)) buckets.set(key, { key, label, rows: [] })
    buckets.get(key)!.rows.push(row)
  }
  return [...buckets.values()].sort((a, b) => {
    if (a.key === 'unassigned') return 1
    if (b.key === 'unassigned') return -1
    return a.label.localeCompare(b.label)
  })
}

const GROUP_LABELS: Record<GroupByOption, string> = {
  none: 'No grouping',
  status: 'Group by status',
  assignee: 'Group by assignee',
  project: 'Group by workspace',
  reviewer: 'Group by reviewer',
  current_responsible: 'Group by current responsible',
}

export function IssueTable({
  tableId,
  selectable = false,
  issues,
  isLoading,
  groupBy = 'none',
  availableGroupBy = ['none', 'status', 'assignee'],
  onGroupByChange,
  showProjectColumn = false,
  projectStatuses,
  emptyMessage = 'No jobs found.',
}: IssueTableProps) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const bulkArchive = useBulkArchive()

  const filtered = useMemo(() => {
    if (!search.trim()) return issues
    const q = search.trim().toLowerCase()
    return issues.filter((i) => i.key.toLowerCase().includes(q) || i.summary.toLowerCase().includes(q))
  }, [issues, search])

  // Selection only ever covers rows currently listed.
  const selectedKeys = useMemo(() => filtered.map((i) => i.key).filter((k) => selected.has(k)), [filtered, selected])
  const allSelected = filtered.length > 0 && selectedKeys.length === filtered.length
  const selectedArchived = filtered.filter((i) => selected.has(i.key) && i.is_archived).length

  const columns = useMemo(
    () =>
      buildColumns(
        showProjectColumn,
        projectStatuses,
        selectable
          ? {
              selected,
              allSelected,
              toggle: (key) =>
                setSelected((prev) => {
                  const next = new Set(prev)
                  if (next.has(key)) next.delete(key)
                  else next.add(key)
                  return next
                }),
              toggleAll: () => setSelected(allSelected ? new Set() : new Set(filtered.map((i) => i.key))),
            }
          : undefined,
      ),
    [showProjectColumn, projectStatuses, selectable, selected, allSelected, filtered],
  )
  // Columns declared by field name (helper.accessor('key', ...)) have no explicit id: TanStack
  // uses the field name, so do the same here.
  const columnIds = useMemo(
    () => columns.map((c) => (c.id ?? (c as { accessorKey?: string }).accessorKey) as string),
    [columns],
  )
  const { layout, handlers, reset, isCustomized } = useTableLayout(tableId, columnIds, {
    columnVisibility: Object.fromEntries(DEFAULT_HIDDEN.map((id) => [id, false])),
  })

  const table = useTable(
    {
      features: issueTableFeatures,
      columns,
      data: filtered,
      columnResizeMode: 'onChange',
      // Each user's saved layout (see useTableLayout); roles and time columns start hidden.
      state: layout,
      ...handlers,
    },
    (state) => state,
  )
  const labelOf = (id: string) => {
    const header = table.getColumn(id)?.columnDef.header
    return typeof header === 'string' ? header : id
  }
  const menuIds = layout.columnOrder.filter((id) => !UTILITY_COLUMNS.includes(id))

  const groups = groupRows(table.getRowModel().rows, groupBy)
  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const i of issues) counts.set(i.status.category, (counts.get(i.status.category) ?? 0) + 1)
    return counts
  }, [issues])

  return (
    <div>
      <div className={styles.countsBar}>
        {(['todo', 'in_progress', 'done'] as const).map((cat) => (
          <span key={cat} className={styles.countChip}>
            <StatusBadge label={CATEGORY_LABELS[cat]} category={cat} /> {statusCounts.get(cat) ?? 0}
          </span>
        ))}
      </div>

      <div className={styles.toolbar}>
        <input
          className={styles.searchInput}
          placeholder="Search by key or summary…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {onGroupByChange && (
          <select
            className={styles.select}
            value={groupBy}
            onChange={(e) => onGroupByChange(e.target.value as GroupByOption)}
          >
            {availableGroupBy.map((g) => (
              <option key={g} value={g}>
                {GROUP_LABELS[g]}
              </option>
            ))}
          </select>
        )}
        <ColumnsMenu
          items={menuIds.map((id) => ({ id, label: labelOf(id), visible: layout.columnVisibility[id] !== false, required: id === 'summary' }))}
          onToggle={(id) => handlers.onColumnVisibilityChange((prev) => ({ ...prev, [id]: prev[id] === false }))}
          onMove={(id, dir) => handlers.onColumnOrderChange((prev) => moveInOrder(prev, id, dir, menuIds))}
          onReset={reset}
          isCustomized={isCustomized}
        />
        {selectable && selectedKeys.length > 0 && (
          <span className={styles.bulkBar}>
            {selectedKeys.length} selected
            {selectedArchived < selectedKeys.length && (
              <button
                type="button"
                className={styles.bulkButton}
                disabled={bulkArchive.isPending}
                onClick={() =>
                  bulkArchive.mutate({ keys: selectedKeys, archived: true }, { onSuccess: () => setSelected(new Set()) })
                }
              >
                <Archive size={13} /> Archive
              </button>
            )}
            {selectedArchived > 0 && (
              <button
                type="button"
                className={styles.bulkButton}
                disabled={bulkArchive.isPending}
                onClick={() =>
                  bulkArchive.mutate({ keys: selectedKeys, archived: false }, { onSuccess: () => setSelected(new Set()) })
                }
              >
                <ArchiveRestore size={13} /> Restore
              </button>
            )}
            <button type="button" className={styles.bulkLink} onClick={() => setSelected(new Set())}>
              Clear
            </button>
          </span>
        )}
        <span style={{ fontSize: 12, color: 'var(--tf-text-subtle)', marginLeft: 'auto' }}>
          {filtered.length} job{filtered.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className={styles.tableScroll}>
        {isLoading ? (
          <div style={{ padding: 'var(--tf-space-3)' }}>
            {[0, 1, 2, 3, 4, 5].map((row) => (
              <div key={row} style={{ display: 'flex', gap: 16, padding: '8px 4px' }}>
                <Skeleton width={16} height={16} />
                <Skeleton width={60} height={12} />
                <Skeleton width="40%" height={12} />
                <Skeleton width={90} height={12} />
                <Skeleton width={110} height={12} />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className={styles.empty}>{emptyMessage}</div>
        ) : (
          <table className={styles.table} style={{ width: table.getTotalSize() }}>
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => {
                    const sorted = header.column.getIsSorted()
                    return (
                      <th
                        key={header.id}
                        className={styles.th}
                        style={{ width: header.getSize() }}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <table.FlexRender header={header} />
                          {sorted === 'asc' && <ArrowUp size={11} />}
                          {sorted === 'desc' && <ArrowDown size={11} />}
                          {!sorted && typeof header.column.columnDef.header === 'string' && header.column.columnDef.header && (
                            <ArrowUpDown size={11} style={{ opacity: 0.25 }} />
                          )}
                        </span>
                        <span
                          className={styles.resizer}
                          onMouseDown={header.getResizeHandler()}
                          onTouchStart={header.getResizeHandler()}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {groups.map((group) => (
                <Fragment key={group.key}>
                  {group.label && (
                    <tr key={`${group.key}-header`} className={styles.groupRow}>
                      <td colSpan={table.getVisibleLeafColumns().length}>
                        {group.label} ({group.rows.length})
                      </td>
                    </tr>
                  )}
                  {group.rows.map((row) => (
                    <tr key={row.id} className={styles.row}>
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className={styles.td} style={{ width: cell.column.getSize() }}>
                          <table.FlexRender cell={cell} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
