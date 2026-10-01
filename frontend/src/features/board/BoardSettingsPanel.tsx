import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { type ReactNode, useMemo, useState } from 'react'

import styles from './BoardSettings.module.css'
import {
  DEFAULT_DUE_DATE_COLORS,
  DEFAULT_PRIORITY_COLORS,
  DUE_DATE_LABELS,
  type DueDateBucket,
  withAlpha,
} from './cardColors'
import { useDeleteBoardStatus, useUpdateBoardConfig } from '@/api/boards'
import { extractErrorMessage } from '@/api/errors'
import { useIssueTypes } from '@/api/issues'
import type {
  Board,
  BoardColumn,
  BoardConfig,
  BoardStatus,
  CardColorRule,
  CardColors,
  CardColorStyle,
  CardFieldKey,
  Priority,
  WorkflowStatus,
} from '@/api/types'
import { Button, Dialog, DialogContent, StatusBadge } from '@/design-system'
import type { StatusCategory } from '@/design-system'
import { CATEGORY_LABELS } from '@/lib/text'

const CARD_FIELD_OPTIONS: { key: CardFieldKey; label: string }[] = [
  { key: 'epic_tag', label: 'Epic tag' },
  { key: 'story_points', label: 'Story points' },
  { key: 'priority', label: 'Priority' },
  { key: 'assignee', label: 'Assignee avatar' },
  { key: 'due_date', label: 'Due date' },
  { key: 'labels', label: 'Labels' },
  { key: 'current_responsible', label: 'Current responsible' },
  { key: 'time_logged', label: 'Time logged vs budget' },
  { key: 'job_value', label: 'Job value' },
]

const CATEGORY_OPTIONS: { value: WorkflowStatus['category']; label: string }[] = [
  { value: 'todo', label: 'To do' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'done', label: 'Done' },
]

// Offered as quick picks next to the full colour picker.
const SWATCHES = ['#0c66e4', '#36b37e', '#ffab00', '#e5493a', '#8777d9', '#00b8d9', '#626f86']

const PRIORITIES: Priority[] = ['highest', 'high', 'medium', 'low', 'lowest']
const DUE_DATE_BUCKETS: DueDateBucket[] = ['overdue', 'due_soon', 'on_track']

/** A column being edited, with a stable local id so drag-reordering never mixes up rows. */
type EditableColumn = BoardColumn & { uid: string }

let uidCounter = 0
const withUid = (col: BoardColumn): EditableColumn => ({ ...col, uid: `col-${++uidCounter}` })

function toPayloadColumn({ uid: _uid, ...col }: EditableColumn): BoardColumn {
  // A column only creates a new status when it maps none of the existing ones.
  if (col.status_ids.length > 0) {
    const { new_status: _unused, ...rest } = col
    return rest
  }
  return { ...col, new_status: col.new_status ?? { category: 'in_progress' } }
}

/** The editable board settings — columns (with new stages), swimlanes, card fields and colour
 * coding. Used inline in Project settings -> Board and inside the board's Configure dialog. */
export function BoardSettingsForm({
  board,
  projectKey,
  onSaved,
  onCancel,
}: {
  board: Board
  projectKey: string
  onSaved?: () => void
  onCancel?: () => void
}) {
  const [columns, setColumns] = useState<EditableColumn[]>(() => board.column_config.map(withUid))
  const [swimlaneMode, setSwimlaneMode] = useState(board.swimlane_mode)
  const [cardFields, setCardFields] = useState<CardFieldKey[]>(board.card_fields)
  const [cardColorRule, setCardColorRule] = useState<CardColorRule>(board.card_color_rule)
  const [cardColorStyle, setCardColorStyle] = useState<CardColorStyle>(board.card_color_style ?? 'stripe')
  const [cardColors, setCardColors] = useState<CardColors>(board.card_colors ?? {})
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const updateConfig = useUpdateBoardConfig(board.id, projectKey)
  const deleteStatus = useDeleteBoardStatus(board.id, projectKey)
  const { data: issueTypes } = useIssueTypes(projectKey)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const columnOfStatus = useMemo(() => {
    const map = new Map<number, string>()
    columns.forEach((c) => c.status_ids.forEach((id) => map.set(id, c.uid)))
    return map
  }, [columns])
  const savedMappedIds = useMemo(
    () => new Set(board.column_config.flatMap((c) => c.status_ids)),
    [board.column_config],
  )
  const unmapped = board.statuses.filter((st) => !columnOfStatus.has(st.id))

  const updateColumn = (uid: string, patch: Partial<BoardColumn>) =>
    setColumns((prev) => prev.map((c) => (c.uid === uid ? { ...c, ...patch } : c)))

  const toggleStatus = (uid: string, statusId: number) =>
    setColumns((prev) =>
      prev.map((c) => {
        if (c.uid !== uid) return c
        const has = c.status_ids.includes(statusId)
        return { ...c, status_ids: has ? c.status_ids.filter((id) => id !== statusId) : [...c.status_ids, statusId] }
      }),
    )

  const handleColumnDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return
    setColumns((prev) => {
      const from = prev.findIndex((c) => c.uid === active.id)
      const to = prev.findIndex((c) => c.uid === over.id)
      if (from === -1 || to === -1) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
  }

  const addColumn = () =>
    setColumns((prev) => [
      ...prev,
      withUid({ name: '', status_ids: [], wip_limit: null, color: null, new_status: { category: 'in_progress' } }),
    ])

  const setOverride = (rule: keyof CardColors, key: string, color: string | null) =>
    setCardColors((prev) => {
      const current = { ...((prev[rule] as Record<string, string> | undefined) ?? {}) }
      if (color) current[key] = color
      else delete current[key]
      return { ...prev, [rule]: current }
    })

  const validate = (): string | null => {
    if (columns.length === 0) return 'A board needs at least one column.'
    const existing = new Set(board.statuses.map((s) => s.name.toLowerCase()))
    const newNames = new Set<string>()
    for (const col of columns) {
      const name = col.name.trim()
      if (!name) return 'Every column needs a name.'
      if (col.status_ids.length === 0) {
        const lower = name.toLowerCase()
        if (existing.has(lower) || newNames.has(lower)) {
          return `A status named "${name}" already exists — tick it on the column instead of creating a new one.`
        }
        newNames.add(lower)
      }
    }
    const hidden = unmapped.filter((s) => s.issue_count > 0)
    if (hidden.length) {
      return `Add ${hidden.map((s) => `"${s.name}"`).join(', ')} to a column first — ${
        hidden.length === 1 ? 'it still has' : 'they still have'
      } jobs that would disappear from the board.`
    }
    return null
  }

  const handleSave = () => {
    setError(null)
    setSavedAt(null)
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }
    updateConfig.mutate(
      {
        column_config: columns.map(toPayloadColumn),
        swimlane_mode: swimlaneMode,
        card_fields: cardFields,
        card_color_rule: cardColorRule,
        card_color_style: cardColorStyle,
        card_colors: cardColors,
      },
      {
        onSuccess: (saved: BoardConfig) => {
          // New columns now have real status ids — re-seed so saving again doesn't try to
          // create those statuses a second time.
          setColumns(saved.column_config.map(withUid))
          setSavedAt(Date.now())
          onSaved?.()
        },
        onError: (err) => setError(extractErrorMessage(err, 'Could not save board settings.').replace(/^\w+: /, '')),
      },
    )
  }

  return (
    <div className={styles.form}>
      <Section title="Columns" hint="Drag to reorder. Each column shows the statuses ticked on it.">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleColumnDragEnd}>
          <SortableContext items={columns.map((c) => c.uid)} strategy={verticalListSortingStrategy}>
            <div className={styles.columnList}>
              {columns.map((col) => (
                <ColumnRow
                  key={col.uid}
                  column={col}
                  statuses={board.statuses}
                  columnOfStatus={columnOfStatus}
                  columnNames={Object.fromEntries(columns.map((c) => [c.uid, c.name || 'Untitled']))}
                  onChange={(patch) => updateColumn(col.uid, patch)}
                  onToggleStatus={(statusId) => toggleStatus(col.uid, statusId)}
                  onRemove={columns.length > 1 ? () => setColumns((p) => p.filter((c) => c.uid !== col.uid)) : undefined}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
        <Button variant="subtle" size="sm" onClick={addColumn} className={styles.addColumn}>
          <Plus size={14} /> Add column
        </Button>
      </Section>

      {unmapped.length > 0 && (
        <Section title="Statuses not on the board" hint="Jobs in these statuses don't appear on any column.">
          <div className={styles.unmappedList}>
            {unmapped.map((st) => (
              <UnmappedStatusRow
                key={st.id}
                status={st}
                canDelete={st.issue_count === 0 && !savedMappedIds.has(st.id)}
                deleting={deleteStatus.isPending && deleteStatus.variables === st.id}
                onDelete={() => deleteStatus.mutate(st.id, { onError: (err) => setError(extractErrorMessage(err)) })}
              />
            ))}
          </div>
        </Section>
      )}

      <Section title="Swimlanes">
        <select
          className={styles.select}
          value={swimlaneMode}
          onChange={(e) => setSwimlaneMode(e.target.value as Board['swimlane_mode'])}
        >
          <option value="none">None</option>
          <option value="epic">By epic</option>
          <option value="assignee">By assignee</option>
          <option value="parent">By parent</option>
        </select>
      </Section>

      <Section title="Card fields">
        <div className={styles.checkGrid}>
          {CARD_FIELD_OPTIONS.map((opt) => (
            <label key={opt.key} className={styles.check}>
              <input
                type="checkbox"
                checked={cardFields.includes(opt.key)}
                onChange={() =>
                  setCardFields((prev) =>
                    prev.includes(opt.key) ? prev.filter((f) => f !== opt.key) : [...prev, opt.key],
                  )
                }
              />
              {opt.label}
            </label>
          ))}
        </div>
      </Section>

      <Section title="Card colour coding">
        <div className={styles.inlineRow}>
          <label className={styles.inlineLabel}>
            Colour cards by
            <select
              className={styles.select}
              value={cardColorRule}
              onChange={(e) => setCardColorRule(e.target.value as CardColorRule)}
            >
              <option value="none">Nothing</option>
              <option value="priority">Priority</option>
              <option value="issue_type">Job type</option>
              <option value="label">First label</option>
              <option value="due_date">Due date</option>
            </select>
          </label>
          {cardColorRule !== 'none' && (
            <div className={styles.segmented} role="radiogroup" aria-label="Colour style">
              {(['stripe', 'tint'] as CardColorStyle[]).map((style) => (
                <button
                  key={style}
                  type="button"
                  role="radio"
                  aria-checked={cardColorStyle === style}
                  data-active={cardColorStyle === style}
                  className={styles.segment}
                  onClick={() => setCardColorStyle(style)}
                >
                  {style === 'stripe' ? 'Left stripe' : 'Tinted card'}
                </button>
              ))}
            </div>
          )}
        </div>

        {cardColorRule === 'priority' &&
          PRIORITIES.map((p) => (
            <ColorValueRow
              key={p}
              label={p[0].toUpperCase() + p.slice(1)}
              defaultColor={DEFAULT_PRIORITY_COLORS[p]}
              override={cardColors.priority?.[p]}
              style={cardColorStyle}
              onChange={(c) => setOverride('priority', p, c)}
            />
          ))}
        {cardColorRule === 'issue_type' &&
          (issueTypes ?? []).map((t) => (
            <ColorValueRow
              key={t.id}
              label={t.name}
              defaultColor={t.color}
              override={cardColors.issue_type?.[String(t.id)]}
              style={cardColorStyle}
              onChange={(c) => setOverride('issue_type', String(t.id), c)}
            />
          ))}
        {cardColorRule === 'due_date' && (
          <>
            {DUE_DATE_BUCKETS.map((b) => (
              <ColorValueRow
                key={b}
                label={DUE_DATE_LABELS[b]}
                defaultColor={DEFAULT_DUE_DATE_COLORS[b]}
                override={cardColors.due_date?.[b]}
                style={cardColorStyle}
                onChange={(c) => setOverride('due_date', b, c)}
              />
            ))}
            <p className={styles.note}>Done jobs and jobs without a due date aren&apos;t coloured.</p>
          </>
        )}
        {cardColorRule === 'label' && (
          <p className={styles.note}>Cards use the colour of their first label, as set on the workspace&apos;s labels.</p>
        )}
      </Section>

      {error && (
        <div className={styles.error} role="alert">
          {error}
        </div>
      )}

      <div className={styles.actions}>
        {savedAt && !updateConfig.isPending && <span className={styles.saved}>Saved.</span>}
        {onCancel && (
          <Button variant="subtle" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button variant="primary" disabled={updateConfig.isPending} onClick={handleSave}>
          {updateConfig.isPending ? 'Saving…' : 'Save board settings'}
        </Button>
      </div>
    </div>
  )
}

interface BoardSettingsPanelProps {
  board: Board
  projectKey: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** The board's "Configure board" dialog. The form is mounted per opening, so an unsaved edit
 * session never leaks into the next one. */
export function BoardSettingsPanel({ board, projectKey, open, onOpenChange }: BoardSettingsPanelProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Configure board" maxWidth={680}>
        {open && (
          <div className={styles.dialogBody}>
            <BoardSettingsForm
              board={board}
              projectKey={projectKey}
              onSaved={() => onOpenChange(false)}
              onCancel={() => onOpenChange(false)}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      {hint && <div className={styles.sectionHint}>{hint}</div>}
      {children}
    </section>
  )
}

function ColorPicker({
  value,
  onChange,
  allowNone = false,
  label,
}: {
  value: string | null | undefined
  onChange: (color: string | null) => void
  allowNone?: boolean
  label: string
}) {
  return (
    <div className={styles.colorPicker}>
      {SWATCHES.map((c) => (
        <button
          key={c}
          type="button"
          className={styles.swatch}
          data-active={value === c}
          style={{ background: c }}
          aria-label={`${label}: ${c}`}
          onClick={() => onChange(c)}
        />
      ))}
      <input
        type="color"
        className={styles.colorInput}
        value={value ?? '#626f86'}
        aria-label={`${label}: custom colour`}
        onChange={(e) => onChange(e.target.value)}
      />
      {allowNone && value && (
        <button type="button" className={styles.iconBtn} aria-label={`${label}: no colour`} onClick={() => onChange(null)}>
          <X size={14} />
        </button>
      )}
    </div>
  )
}

function ColorValueRow({
  label,
  defaultColor,
  override,
  style,
  onChange,
}: {
  label: string
  defaultColor: string
  override: string | undefined
  style: CardColorStyle
  onChange: (color: string | null) => void
}) {
  const color = override ?? defaultColor
  const tint = style === 'tint' ? withAlpha(color, 0.14) : undefined
  return (
    <div className={styles.colorRow}>
      <div className={styles.preview} style={{ borderLeftColor: color, background: tint !== color ? tint : undefined }}>
        {label}
      </div>
      <ColorPicker value={color} label={label} onChange={(c) => onChange(c && c !== defaultColor ? c : null)} />
      {override && (
        <button type="button" className={styles.iconBtn} aria-label={`Reset ${label} colour`} onClick={() => onChange(null)}>
          <RotateCcw size={14} />
        </button>
      )}
    </div>
  )
}

function ColumnRow({
  column,
  statuses,
  columnOfStatus,
  columnNames,
  onChange,
  onToggleStatus,
  onRemove,
}: {
  column: EditableColumn
  statuses: BoardStatus[]
  columnOfStatus: Map<number, string>
  columnNames: Record<string, string>
  onChange: (patch: Partial<BoardColumn>) => void
  onToggleStatus: (statusId: number) => void
  onRemove?: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: column.uid })
  const createsStatus = column.status_ids.length === 0

  return (
    <div
      ref={setNodeRef}
      className={styles.columnRow}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        borderTopColor: column.color ?? undefined,
      }}
    >
      <div className={styles.columnTop}>
        <span {...attributes} {...listeners} className={styles.grip} aria-label="Drag to reorder">
          <GripVertical size={16} />
        </span>
        <input
          className={styles.input}
          style={{ flex: 1 }}
          value={column.name}
          placeholder="Column name, e.g. QA"
          aria-label="Column name"
          maxLength={100}
          onChange={(e) => onChange({ name: e.target.value })}
        />
        <input
          type="number"
          min={1}
          placeholder="WIP limit"
          aria-label="WIP limit"
          className={styles.input}
          style={{ width: 96 }}
          value={column.wip_limit ?? ''}
          onChange={(e) => onChange({ wip_limit: e.target.value ? Number(e.target.value) : null })}
        />
        {onRemove && (
          <Button variant="subtle" size="sm" iconOnly aria-label="Remove column" onClick={onRemove}>
            <Trash2 size={14} />
          </Button>
        )}
      </div>

      <div className={styles.columnDetail}>
        <span className={styles.detailLabel}>Colour</span>
        <ColorPicker
          value={column.color}
          allowNone
          label={`${column.name || 'Column'} colour`}
          onChange={(color) => onChange({ color })}
        />
      </div>

      <div className={styles.columnDetail}>
        <span className={styles.detailLabel}>Statuses</span>
        <div className={styles.statusChecks}>
          {statuses.map((status) => {
            const owner = columnOfStatus.get(status.id)
            const elsewhere = owner !== undefined && owner !== column.uid
            return (
              <label
                key={status.id}
                className={styles.check}
                data-disabled={elsewhere}
                title={elsewhere ? `Already in "${columnNames[owner]}"` : undefined}
              >
                <input
                  type="checkbox"
                  disabled={elsewhere}
                  checked={column.status_ids.includes(status.id)}
                  onChange={() => onToggleStatus(status.id)}
                />
                {status.name}
              </label>
            )
          })}
        </div>
      </div>

      {createsStatus && (
        <div className={styles.newStatus}>
          Saving creates a new status <strong>“{column.name.trim() || 'Untitled'}”</strong> for this column, counted as
          <select
            className={styles.select}
            aria-label="New status category"
            value={column.new_status?.category ?? 'in_progress'}
            onChange={(e) => onChange({ new_status: { category: e.target.value as WorkflowStatus['category'] } })}
          >
            {CATEGORY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}

function UnmappedStatusRow({
  status,
  canDelete,
  deleting,
  onDelete,
}: {
  status: BoardStatus
  canDelete: boolean
  deleting: boolean
  onDelete: () => void
}) {
  return (
    <div className={styles.unmappedRow}>
      <span className={styles.unmappedName}>{status.name}</span>
      <StatusBadge label={CATEGORY_LABELS[status.category]} category={status.category as StatusCategory} />
      {status.issue_count > 0 ? (
        <span className={styles.warn}>
          {status.issue_count} job{status.issue_count === 1 ? '' : 's'} hidden — tick it on a column
        </span>
      ) : canDelete ? (
        <Button variant="subtle" size="sm" disabled={deleting} onClick={onDelete}>
          <Trash2 size={14} /> {deleting ? 'Deleting…' : 'Delete status'}
        </Button>
      ) : (
        <span className={styles.muted}>Save first, then you can delete it</span>
      )}
    </div>
  )
}
