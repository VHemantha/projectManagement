import { type ColumnDef, type RowData, createColumnHelper, useTable } from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ArrowUpDown, Download } from 'lucide-react'
import { type ReactNode, useMemo } from 'react'

import { ColumnsMenu } from './ColumnsMenu'
import styles from './DataTable.module.css'
import { Skeleton } from '@/design-system'
import { moveInOrder } from '@/lib/columnOrder'
import { downloadCsv } from '@/lib/csv'
import { dataTableFeatures } from '@/lib/tableFeatures'
import { useTableLayout } from '@/lib/useTableLayout'

type CellValue = string | number | boolean | null | undefined

export interface DataColumn<T extends RowData> {
  id: string
  label: string
  /** The raw value: used to sort, to export, and (without `cell`) to display. */
  value: (row: T) => CellValue
  /** Custom display for the cell. */
  cell?: (row: T) => ReactNode
  /** Hidden until the user adds it from the Columns menu. */
  defaultHidden?: boolean
  /** Can't be hidden (e.g. the row's name). */
  required?: boolean
  numeric?: boolean
  size?: number
}

function display(value: CellValue): ReactNode {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return value
}

/** A customisable, sortable table: click a header to sort, the Columns menu to show/hide and
 * reorder columns, drag a header edge to resize, and Export CSV for exactly what's shown.
 * Each user's layout is saved per `tableId`. */
export function DataTable<T extends RowData>({
  tableId,
  columns,
  data,
  getRowId,
  isLoading,
  emptyMessage = 'Nothing to show.',
  onRowClick,
  toolbar,
  exportName,
  defaultSort,
  countLabel = (n) => `${n} row${n === 1 ? '' : 's'}`,
}: {
  tableId: string
  columns: DataColumn<T>[]
  data: T[]
  getRowId: (row: T) => string
  isLoading?: boolean
  emptyMessage?: string
  onRowClick?: (row: T) => void
  toolbar?: ReactNode
  /** File name (without .csv) for Export CSV; omit to hide the button. */
  exportName?: string
  defaultSort?: { id: string; desc: boolean }[]
  countLabel?: (n: number) => string
}) {
  const columnIds = useMemo(() => columns.map((c) => c.id), [columns])
  const { layout, handlers, reset, isCustomized } = useTableLayout(tableId, columnIds, {
    sorting: defaultSort,
    columnVisibility: Object.fromEntries(columns.filter((c) => c.defaultHidden).map((c) => [c.id, false])),
  })

  const tableColumns = useMemo(() => {
    const helper = createColumnHelper<typeof dataTableFeatures, T>()
    // Mixed value types per column, as TanStack's docs recommend typing a column array.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return columns.map((col): ColumnDef<typeof dataTableFeatures, T, any> =>
      helper.accessor((row) => col.value(row) ?? undefined, {
        id: col.id,
        header: col.label,
        size: col.size ?? (col.numeric ? 110 : 180),
        sortFn: col.numeric ? 'basic' : 'alphanumeric',
        sortUndefined: 'last',
        cell: (ctx) => (col.cell ? col.cell(ctx.row.original) : display(col.value(ctx.row.original))),
      }),
    )
  }, [columns])

  const table = useTable(
    {
      features: dataTableFeatures,
      columns: tableColumns,
      data,
      getRowId,
      columnResizeMode: 'onChange',
      state: layout,
      ...handlers,
    },
    (state) => state,
  )

  const byId = useMemo(() => new Map(columns.map((c) => [c.id, c])), [columns])
  const visibleColumns = layout.columnOrder.filter((id) => layout.columnVisibility[id] !== false).map((id) => byId.get(id)!)

  const exportCsv = () => {
    const rows = table.getRowModel().rows.map((row) => visibleColumns.map((c) => {
      const v = c.value(row.original)
      return typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v
    }))
    downloadCsv(`${exportName}.csv`, visibleColumns.map((c) => c.label), rows)
  }

  const numericIds = new Set(columns.filter((c) => c.numeric).map((c) => c.id))

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        {toolbar}
        <ColumnsMenu
          items={layout.columnOrder.map((id) => ({
            id,
            label: byId.get(id)!.label,
            visible: layout.columnVisibility[id] !== false,
            required: byId.get(id)!.required,
          }))}
          onToggle={(id) => handlers.onColumnVisibilityChange((prev) => ({ ...prev, [id]: prev[id] === false }))}
          onMove={(id, dir) => handlers.onColumnOrderChange((prev) => moveInOrder(prev, id, dir, prev))}
          onReset={reset}
          isCustomized={isCustomized}
        />
        {exportName && (
          <button type="button" className={styles.toolButton} onClick={exportCsv} disabled={data.length === 0}>
            <Download size={14} /> Export CSV
          </button>
        )}
        <span className={styles.count}>{countLabel(data.length)}</span>
      </div>

      <div className={styles.scroll}>
        {isLoading ? (
          <div className={styles.loading}>
            {[0, 1, 2, 3].map((r) => (
              <Skeleton key={r} height={12} width={r % 2 ? '60%' : '85%'} />
            ))}
          </div>
        ) : data.length === 0 ? (
          <div className={styles.empty}>{emptyMessage}</div>
        ) : (
          <table className={styles.table} style={{ width: table.getTotalSize() }}>
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => {
                    const sorted = header.column.getIsSorted()
                    return (
                      <th
                        key={header.id}
                        style={{ width: header.getSize() }}
                        className={numericIds.has(header.column.id) ? styles.numeric : undefined}
                        onClick={header.column.getToggleSortingHandler()}
                        aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none'}
                      >
                        <span className={styles.headerLabel}>
                          <table.FlexRender header={header} />
                          {sorted === 'asc' && <ArrowUp size={11} />}
                          {sorted === 'desc' && <ArrowDown size={11} />}
                          {!sorted && <ArrowUpDown size={11} className={styles.sortHint} />}
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
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={onRowClick ? styles.clickable : undefined}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      style={{ width: cell.column.getSize() }}
                      className={numericIds.has(cell.column.id) ? styles.numeric : undefined}
                    >
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
