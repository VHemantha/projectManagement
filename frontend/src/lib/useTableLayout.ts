import type { Updater } from '@tanstack/react-table'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useSaveTablePreference, useTablePreferences } from '@/api/tablePreferences'

export interface TableLayout {
  sorting: { id: string; desc: boolean }[]
  columnVisibility: Record<string, boolean>
  columnOrder: string[]
  columnSizing: Record<string, number>
}

const SAVE_DELAY_MS = 600

const resolve = <T,>(updater: Updater<T>, current: T): T =>
  typeof updater === 'function' ? (updater as (old: T) => T)(current) : updater

/** Keep saved state in line with the table's current columns: drop ids that no longer exist,
 * and append new columns (in their default position order) to the saved order. */
function reconcile(layout: TableLayout, columnIds: string[]): TableLayout {
  const known = new Set(columnIds)
  const order = layout.columnOrder.filter((id) => known.has(id))
  for (const id of columnIds) if (!order.includes(id)) order.push(id)
  return {
    sorting: layout.sorting.filter((s) => known.has(s.id)),
    columnVisibility: Object.fromEntries(Object.entries(layout.columnVisibility).filter(([id]) => known.has(id))),
    columnOrder: order,
    columnSizing: Object.fromEntries(Object.entries(layout.columnSizing).filter(([id]) => known.has(id))),
  }
}

/** One user's layout for one table — sort, visible columns, order and widths — saved on the
 * server (so it follows them between devices) and restored next time. `defaults` is the
 * table's out-of-the-box layout, which "Reset" returns to. */
export function useTableLayout(tableId: string, columnIds: string[], defaults: Partial<TableLayout> = {}) {
  const { data: prefs } = useTablePreferences()
  const save = useSaveTablePreference()
  const idsKey = columnIds.join('|')

  const defaultLayout = useMemo<TableLayout>(
    () =>
      reconcile(
        {
          sorting: defaults.sorting ?? [],
          columnVisibility: defaults.columnVisibility ?? {},
          columnOrder: defaults.columnOrder ?? columnIds,
          columnSizing: defaults.columnSizing ?? {},
        },
        columnIds,
      ),
    // Defaults are static per table; re-derive only when the set of columns changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [idsKey],
  )
  const saved = prefs?.[tableId] as Partial<TableLayout> | undefined
  const base = useMemo(
    () => (saved ? reconcile({ ...defaultLayout, ...saved }, columnIds) : defaultLayout),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [saved, defaultLayout],
  )

  // Local edits win over the saved copy until the next mount.
  const [local, setLocal] = useState<TableLayout | null>(null)
  const layout = local ? reconcile(local, columnIds) : base

  const dirty = useRef(false)
  useEffect(() => {
    if (!local || !dirty.current) return undefined
    const timer = setTimeout(() => {
      dirty.current = false
      void save(tableId, local as unknown as Record<string, unknown>)
    }, SAVE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [local, save, tableId])

  const change = useCallback(
    <K extends keyof TableLayout>(slice: K) =>
      (updater: Updater<TableLayout[K]>) => {
        dirty.current = true
        setLocal((prev) => {
          const current = prev ?? base
          return { ...current, [slice]: resolve(updater, current[slice]) }
        })
      },
    [base],
  )

  const reset = useCallback(() => {
    dirty.current = false
    setLocal(null)
    void save(tableId, null)
  }, [save, tableId])

  const isCustomized = !!local || !!saved

  return {
    layout,
    handlers: {
      onSortingChange: change('sorting'),
      onColumnVisibilityChange: change('columnVisibility'),
      onColumnOrderChange: change('columnOrder'),
      onColumnSizingChange: change('columnSizing'),
    },
    reset,
    isCustomized,
  }
}
