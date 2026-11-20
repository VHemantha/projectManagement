import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useMemo, useState } from 'react'

import styles from './BoardSettings.module.css'
import { BoardSettingsForm } from './BoardSettingsPanel'
import { apiClient } from '@/api/client'
import { extractErrorMessage } from '@/api/errors'
import type { Board, BoardColumn, WorkflowStatus } from '@/api/types'
import { Button, Dialog, DialogContent } from '@/design-system'

const CATEGORIES: { value: WorkflowStatus['category']; label: string }[] = [
  { value: 'todo', label: 'To do' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'done', label: 'Done' },
]

const sameName = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase()

/** A board's columns with `name` added after the column called `after` (at the end when
 * the board has no such column). An existing status with that name is reused, so a stage
 * the board once had comes back instead of a second one being made. */
export function withColumn(board: Board, name: string, category: WorkflowStatus['category'], after: string): BoardColumn[] {
  const status = board.statuses.find((s) => sameName(s.name, name))
  const column: BoardColumn = status
    ? { name, status_ids: [status.id], wip_limit: null }
    : { name, status_ids: [], wip_limit: null, new_status: { category } }
  const columns = [...board.column_config]
  const at = columns.findIndex((c) => sameName(c.name, after))
  columns.splice(at === -1 ? columns.length : at + 1, 0, column)
  return columns
}

/** The Workspaces board's column settings. The board shows the tasks of several projects, each
 * with its own columns, so a new column goes onto every board in view the user may change, and
 * any one board can be opened in the full editor (rename, reorder, colour, remove). */
export function BoardColumnsDialog({
  open,
  onOpenChange,
  projectKeys,
  boards,
  projectNames,
  columnNames,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectKeys: string[]
  boards: Record<string, Board>
  projectNames: Record<string, string>
  /** The columns the board shows now, to place a new column after. */
  columnNames: string[]
}) {
  const editable = projectKeys.filter((k) => boards[k]?.can_configure)
  const locked = projectKeys.filter((k) => boards[k] && !boards[k].can_configure)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Board columns" maxWidth={720}>
        {open && (
          <div className={styles.dialogBody}>
            {projectKeys.length === 0 ? (
              <p className={styles.sectionHint}>There are no tasks on this board yet, so there are no boards to change.</p>
            ) : editable.length === 0 ? (
              <p className={styles.sectionHint}>
                Only a project lead, a project admin or an organisation admin can change these columns.
              </p>
            ) : (
              <ColumnsBody
                editable={editable}
                locked={locked}
                boards={boards}
                projectNames={projectNames}
                columnNames={columnNames}
                onDone={() => onOpenChange(false)}
              />
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ColumnsBody({
  editable,
  locked,
  boards,
  projectNames,
  columnNames,
  onDone,
}: {
  editable: string[]
  locked: string[]
  boards: Record<string, Board>
  projectNames: Record<string, string>
  columnNames: string[]
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const label = (key: string) => (projectNames[key] ? `${projectNames[key]} (${key})` : key)
  // Default place: before the first column whose stages are all done (Complete, To be Archived).
  const firstDone = useMemo(() => {
    const board = boards[editable[0]]
    if (!board) return ''
    const category = new Map(board.statuses.map((s) => [s.id, s.category]))
    const i = board.column_config.findIndex((c) => c.status_ids.length > 0 && c.status_ids.every((id) => category.get(id) === 'done'))
    return i > 0 ? board.column_config[i - 1].name : ''
  }, [boards, editable])

  const [name, setName] = useState('')
  const [category, setCategory] = useState<WorkflowStatus['category']>('in_progress')
  const [after, setAfter] = useState<string>(firstDone || columnNames[columnNames.length - 1] || '')
  const [editing, setEditing] = useState<string>(editable.length === 1 ? editable[0] : '')
  const [done, setDone] = useState<string | null>(null)

  const addColumn = useMutation({
    mutationFn: async () => {
      const clean = name.trim()
      const added: string[] = []
      for (const key of editable) {
        const board = boards[key]
        if (board.column_config.some((c) => sameName(c.name, clean))) continue
        await apiClient.patch(`/boards/${board.id}/config/`, { column_config: withColumn(board, clean, category, after) })
        added.push(key)
      }
      return added
    },
    onSettled: (added) => {
      for (const key of added ?? editable) queryClient.invalidateQueries({ queryKey: ['projects', key, 'board'] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
    onSuccess: (added) => {
      setDone(
        added.length
          ? `"${name.trim()}" added to ${added.length} board${added.length === 1 ? '' : 's'}.`
          : `Every board here already has a "${name.trim()}" column.`,
      )
      setName('')
    },
  })

  return (
    <>
      <section className={styles.section}>
        <div className={styles.sectionTitle}>Add a column</div>
        <div className={styles.sectionHint}>
          {editable.length === 1
            ? `Added to the ${label(editable[0])} board.`
            : `Added to all ${editable.length} boards on this view, so it shows as one column here.`}
          {locked.length > 0 && ` Not added to ${locked.map(label).join(', ')}: you can't change ${locked.length === 1 ? 'that board' : 'those boards'}.`}
        </div>
        <form
          style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim() || addColumn.isPending) return
            setDone(null)
            addColumn.mutate()
          }}
        >
          <label style={{ display: 'grid', gap: 4, flex: '1 1 180px' }}>
            <span className={styles.sectionHint}>Column name</span>
            <input className={styles.input} value={name} maxLength={50} onChange={(e) => setName(e.target.value)} placeholder="e.g. Partner review" />
          </label>
          <label style={{ display: 'grid', gap: 4 }}>
            <span className={styles.sectionHint}>Counts as</span>
            <select className={styles.select} value={category} onChange={(e) => setCategory(e.target.value as WorkflowStatus['category'])}>
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: 'grid', gap: 4 }}>
            <span className={styles.sectionHint}>Place after</span>
            <select className={styles.select} value={after} onChange={(e) => setAfter(e.target.value)}>
              {columnNames.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" variant="primary" size="sm" disabled={!name.trim() || addColumn.isPending}>
            <Plus size={14} /> {addColumn.isPending ? 'Adding…' : 'Add column'}
          </Button>
        </form>
        {addColumn.isError && <div className={styles.error}>{extractErrorMessage(addColumn.error)}</div>}
        {done && <div className={styles.sectionHint} role="status">{done}</div>}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionTitle}>Edit a board</div>
        <div className={styles.sectionHint}>Rename, reorder, colour or remove columns, and choose what the cards show.</div>
        {editable.length > 1 && (
          <select className={styles.select} value={editing} onChange={(e) => setEditing(e.target.value)} aria-label="Board to edit">
            <option value="">Choose a board…</option>
            {editable.map((k) => (
              <option key={k} value={k}>
                {label(k)}
              </option>
            ))}
          </select>
        )}
      </section>
      {editing && boards[editing] && (
        <BoardSettingsForm key={editing} board={boards[editing]} projectKey={editing} onSaved={onDone} onCancel={onDone} />
      )}
    </>
  )
}
