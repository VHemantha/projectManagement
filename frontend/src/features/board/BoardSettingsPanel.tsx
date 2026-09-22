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
import { GripVertical, Plus, Trash2 } from 'lucide-react'
import { type CSSProperties, useEffect, useState } from 'react'

import { useUpdateBoardConfig } from '@/api/boards'
import type { Board, BoardColumn, CardColorRule, CardFieldKey } from '@/api/types'
import { Button, Dialog, DialogContent } from '@/design-system'

const CARD_FIELD_OPTIONS: { key: CardFieldKey; label: string }[] = [
  { key: 'epic_tag', label: 'Epic tag' },
  { key: 'story_points', label: 'Story points' },
  { key: 'priority', label: 'Priority' },
  { key: 'assignee', label: 'Assignee avatar' },
  { key: 'due_date', label: 'Due date' },
  { key: 'labels', label: 'Labels' },
  { key: 'current_responsible', label: 'Current responsible' },
]

const inputStyle: CSSProperties = {
  height: 32,
  borderRadius: 4,
  border: '1px solid var(--tf-border)',
  padding: '0 8px',
  fontSize: 13,
  background: 'var(--tf-surface)',
  color: 'var(--tf-text)',
}

interface BoardSettingsPanelProps {
  board: Board
  projectKey: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function BoardSettingsPanel({ board, projectKey, open, onOpenChange }: BoardSettingsPanelProps) {
  const [columns, setColumns] = useState<BoardColumn[]>(board.column_config)
  const [swimlaneMode, setSwimlaneMode] = useState(board.swimlane_mode)
  const [cardFields, setCardFields] = useState<CardFieldKey[]>(board.card_fields)
  const [cardColorRule, setCardColorRule] = useState<CardColorRule>(board.card_color_rule)
  const [error, setError] = useState<string | null>(null)
  const updateConfig = useUpdateBoardConfig(board.id, projectKey)

  // Re-seed local edit state whenever the dialog is (re)opened, so a previous edit session
  // that wasn't saved doesn't leak into the next one.
  useEffect(() => {
    if (open) {
      setColumns(board.column_config)
      setSwimlaneMode(board.swimlane_mode)
      setCardFields(board.card_fields)
      setCardColorRule(board.card_color_rule)
      setError(null)
    }
  }, [open, board])

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const handleColumnDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    setColumns((prev) => {
      const oldIndex = prev.findIndex((_, i) => `col-${i}` === active.id)
      const newIndex = prev.findIndex((_, i) => `col-${i}` === over.id)
      if (oldIndex === -1 || newIndex === -1) return prev
      const next = [...prev]
      const [moved] = next.splice(oldIndex, 1)
      next.splice(newIndex, 0, moved)
      return next
    })
  }

  const updateColumn = (index: number, patch: Partial<BoardColumn>) => {
    setColumns((prev) => prev.map((c, i) => (i === index ? { ...c, ...patch } : c)))
  }

  const toggleStatus = (index: number, statusId: number) => {
    setColumns((prev) =>
      prev.map((c, i) => {
        if (i !== index) return c
        const has = c.status_ids.includes(statusId)
        return { ...c, status_ids: has ? c.status_ids.filter((id) => id !== statusId) : [...c.status_ids, statusId] }
      }),
    )
  }

  const addColumn = () => {
    setColumns((prev) => [...prev, { name: 'New column', status_ids: [], wip_limit: null }])
  }

  const removeColumn = (index: number) => {
    setColumns((prev) => prev.filter((_, i) => i !== index))
  }

  const toggleCardField = (key: CardFieldKey) => {
    setCardFields((prev) => (prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key]))
  }

  const handleSave = () => {
    setError(null)
    if (columns.length === 0) {
      setError('A board needs at least one column.')
      return
    }
    for (const col of columns) {
      if (!col.name.trim()) {
        setError('Every column needs a name.')
        return
      }
      if (col.status_ids.length === 0) {
        setError(`Column "${col.name}" needs at least one status — cards can't be moved into an empty column.`)
        return
      }
    }
    updateConfig.mutate(
      { column_config: columns, swimlane_mode: swimlaneMode, card_fields: cardFields, card_color_rule: cardColorRule },
      {
        onSuccess: () => onOpenChange(false),
        onError: () => setError('Could not save board settings — you may not have permission to configure this board.'),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Configure board" maxWidth={620}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxHeight: '70vh', overflowY: 'auto' }}>
          <section>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Columns and swimlanes</div>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleColumnDragEnd}>
              <SortableContext items={columns.map((_, i) => `col-${i}`)} strategy={verticalListSortingStrategy}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {columns.map((col, index) => (
                    <ColumnRow
                      key={`col-${index}`}
                      id={`col-${index}`}
                      column={col}
                      statuses={board.statuses}
                      onChange={(patch) => updateColumn(index, patch)}
                      onToggleStatus={(statusId) => toggleStatus(index, statusId)}
                      onRemove={columns.length > 1 ? () => removeColumn(index) : undefined}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
            <Button variant="subtle" size="sm" onClick={addColumn} style={{ marginTop: 8 }}>
              <Plus size={14} /> Add column
            </Button>
          </section>

          <section>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Swimlanes</div>
            <select
              style={inputStyle}
              value={swimlaneMode}
              onChange={(e) => setSwimlaneMode(e.target.value as Board['swimlane_mode'])}
            >
              <option value="none">None</option>
              <option value="epic">By epic</option>
              <option value="assignee">By assignee</option>
              <option value="parent">By parent</option>
            </select>
          </section>

          <section>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Card fields</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px' }}>
              {CARD_FIELD_OPTIONS.map((opt) => (
                <label key={opt.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={cardFields.includes(opt.key)}
                    onChange={() => toggleCardField(opt.key)}
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </section>

          <section>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Color cards by</div>
            <select style={inputStyle} value={cardColorRule} onChange={(e) => setCardColorRule(e.target.value as CardColorRule)}>
              <option value="none">Nothing</option>
              <option value="priority">Priority</option>
              <option value="issue_type">Issue type</option>
              <option value="label">First label</option>
            </select>
          </section>

          {error && <div style={{ color: 'var(--tf-danger)', fontSize: 13 }}>{error}</div>}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={updateConfig.isPending} onClick={handleSave}>
              Save
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ColumnRow({
  id,
  column,
  statuses,
  onChange,
  onToggleStatus,
  onRemove,
}: {
  id: string
  column: BoardColumn
  statuses: Board['statuses']
  onChange: (patch: Partial<BoardColumn>) => void
  onToggleStatus: (statusId: number) => void
  onRemove?: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={{
        ...style,
        border: '1px solid var(--tf-border)',
        borderRadius: 6,
        padding: 10,
        background: 'var(--tf-surface)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span {...attributes} {...listeners} style={{ cursor: 'grab', color: 'var(--tf-text-subtle)' }}>
          <GripVertical size={16} />
        </span>
        <input
          style={{ ...inputStyle, flex: 1 }}
          value={column.name}
          onChange={(e) => onChange({ name: e.target.value })}
        />
        <input
          type="number"
          min={1}
          placeholder="WIP limit"
          style={{ ...inputStyle, width: 90 }}
          value={column.wip_limit ?? ''}
          onChange={(e) => onChange({ wip_limit: e.target.value ? Number(e.target.value) : null })}
        />
        {onRemove && (
          <Button variant="subtle" size="sm" iconOnly aria-label="Remove column" onClick={onRemove}>
            <Trash2 size={14} />
          </Button>
        )}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', paddingLeft: 24 }}>
        {statuses.map((status) => (
          <label key={status.id} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={column.status_ids.includes(status.id)}
              onChange={() => onToggleStatus(status.id)}
            />
            {status.name}
          </label>
        ))}
      </div>
    </div>
  )
}
