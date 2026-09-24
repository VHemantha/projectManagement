import { Plus, X } from 'lucide-react'
import { type KeyboardEvent, useState } from 'react'

import styles from './TaskNamesEditor.module.css'
import { Button } from '@/design-system'

/** Edits a project's list of standard task names (Project.task_names). Used when creating a
 * project and in its settings; the Create issue dialog then offers these as the summary. */
export function TaskNamesEditor({
  value,
  onChange,
  id = 'task-names',
}: {
  value: string[]
  onChange: (next: string[]) => void
  id?: string
}) {
  const [draft, setDraft] = useState('')
  const trimmed = draft.trim().replace(/\s+/g, ' ')
  const isDuplicate = value.some((t) => t.toLowerCase() === trimmed.toLowerCase())

  const add = () => {
    if (!trimmed || isDuplicate) return
    onChange([...value, trimmed])
    setDraft('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    // Enter adds a task instead of submitting the surrounding form.
    if (e.key === 'Enter') {
      e.preventDefault()
      add()
    }
  }

  return (
    <div className={styles.editor}>
      <div className={styles.addRow}>
        <input
          id={id}
          className={styles.input}
          value={draft}
          maxLength={500}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. Bank reconciliation — press Enter to add"
        />
        <Button type="button" variant="secondary" size="sm" onClick={add} disabled={!trimmed || isDuplicate}>
          <Plus size={14} /> Add
        </Button>
      </div>
      {isDuplicate && trimmed && <span className={styles.hint}>“{trimmed}” is already in the list.</span>}
      {value.length === 0 ? (
        <span className={styles.empty}>No tasks yet. Issues can still be created with a custom summary.</span>
      ) : (
        <ul className={styles.list}>
          {value.map((task) => (
            <li key={task} className={styles.item}>
              <span className={styles.itemName}>{task}</span>
              <button
                type="button"
                className={styles.remove}
                aria-label={`Remove ${task}`}
                onClick={() => onChange(value.filter((t) => t !== task))}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
