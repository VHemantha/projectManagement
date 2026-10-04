import { type KeyboardEvent, type SyntheticEvent, useState } from 'react'

import styles from './KanbanBoard.module.css'
import { usePatchIssueField } from '@/api/issues'
import type { IssueListItem } from '@/api/types'

// Clicks and presses inside the editor must not open the job or start a card drag.
const stop = (e: SyntheticEvent) => e.stopPropagation()

export function formatValue(value: string | null, currency: string) {
  if (value == null || value === '') return null
  return `${currency} ${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

/** The job's value, shown on its card and editable in place: click it, type, Enter to save
 * (Escape cancels, clearing the box removes the value). */
export function CardValue({ issue }: { issue: IssueListItem }) {
  const patch = usePatchIssueField()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const shown = formatValue(issue.allocated_value, issue.value_currency)

  const save = () => {
    setEditing(false)
    const next = draft.trim() === '' ? null : String(Number(draft))
    if (next !== null && Number.isNaN(Number(next))) return
    const current = issue.allocated_value == null ? null : String(Number(issue.allocated_value))
    if (next !== current) patch.mutate({ key: issue.key, patch: { allocated_value: next } })
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    e.stopPropagation()
    if (e.key === 'Enter') save()
    if (e.key === 'Escape') setEditing(false)
  }

  if (editing) {
    return (
      <label className={styles.cardValue} onClick={stop} onPointerDown={stop}>
        <span className={styles.cardValueCurrency}>{issue.value_currency}</span>
        <input
          className={styles.cardValueInput}
          type="number"
          min={0}
          step="0.01"
          autoFocus
          aria-label={`Task value for ${issue.key}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={save}
        />
      </label>
    )
  }

  return (
    <button
      type="button"
      className={styles.cardValueButton}
      data-empty={!shown}
      aria-label={shown ? `Task value ${shown}, click to edit` : `Add task value for ${issue.key}`}
      title="Task value"
      onPointerDown={stop}
      onClick={(e) => {
        stop(e)
        setDraft(issue.allocated_value == null ? '' : String(Number(issue.allocated_value)))
        setEditing(true)
      }}
    >
      {shown ?? '+ Add value'}
    </button>
  )
}
