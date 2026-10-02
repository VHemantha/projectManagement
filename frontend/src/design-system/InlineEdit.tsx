import { Pencil } from 'lucide-react'
import { type ElementType, type KeyboardEvent, useEffect, useRef, useState } from 'react'

import styles from './InlineEdit.module.css'
import { extractErrorMessage } from '@/api/errors'

interface InlineEditProps {
  /** The saved name. */
  value: string
  /** Persist a new name; reject to roll the optimistic change back and show the error. */
  onSave: (next: string) => Promise<unknown>
  /** What is being named, e.g. "Workspace name" — the input's label and the edit button's name. */
  label: string
  /** Users who may not rename see plain text. */
  canEdit?: boolean
  /** Enter edit mode on click (default) or double-click, for text that is also a click target. */
  activation?: 'click' | 'doubleClick'
  maxLength?: number
  /** Extra client-side check (non-empty and max length are built in); return an error or null. */
  validate?: (next: string) => string | null
  as?: ElementType
  className?: string
}

const ERROR_MS = 5000

const tidy = (text: string) => text.split(/\s+/).filter(Boolean).join(' ')

/**
 * A name that can be renamed where it is shown: click (or double-click) it, type, Enter or
 * leaving the box saves, Esc cancels. The new name shows straight away and rolls back if
 * saving fails.
 */
export function InlineEdit({
  value,
  onSave,
  label,
  canEdit = true,
  activation = 'click',
  maxLength = 150,
  validate,
  as: Tag = 'span',
  className,
}: InlineEditProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)
  // Optimistic name, shown until the saved value catches up (or the save fails).
  const [pending, setPending] = useState<{ name: string; from: string } | null>(null)
  const done = useRef(false)

  if (pending && value !== pending.from) setPending(null)
  const shown = pending?.name ?? value

  // A failed save's message fades after a few seconds; while editing it stays until fixed.
  useEffect(() => {
    if (!error || editing) return
    const timer = setTimeout(() => setError(null), ERROR_MS)
    return () => clearTimeout(timer)
  }, [error, editing])

  const start = () => {
    if (!canEdit) return
    done.current = false
    setDraft(shown)
    setError(null)
    setEditing(true)
  }

  const cancel = () => {
    done.current = true
    setEditing(false)
    setError(null)
  }

  const commit = () => {
    if (done.current) return
    const next = tidy(draft)
    if (next === shown) return cancel()
    const problem = !next
      ? `${label} can't be empty.`
      : next.length > maxLength
        ? `${label} can be at most ${maxLength} characters.`
        : (validate?.(next) ?? null)
    if (problem) {
      setError(problem)
      return
    }
    done.current = true
    setEditing(false)
    setError(null)
    setPending({ name: next, from: value })
    onSave(next).catch((err: unknown) => {
      setPending(null)
      setError(extractErrorMessage(err))
    })
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      cancel()
    }
  }

  if (editing) {
    return (
      <span className={styles.editing}>
        <input
          className={`${styles.input} ${className ?? ''}`}
          aria-label={label}
          aria-invalid={!!error}
          value={draft}
          maxLength={maxLength + 50}
          autoFocus
          onFocus={(e) => e.target.select()}
          onChange={(e) => {
            setDraft(e.target.value)
            setError(null)
          }}
          onKeyDown={onKeyDown}
          onBlur={commit}
          onClick={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
        />
        {error && (
          <span role="alert" className={styles.error}>
            {error}
          </span>
        )}
      </span>
    )
  }

  return (
    <span className={styles.wrap}>
      <Tag
        className={`${className ?? ''} ${canEdit ? styles.editable : ''}`}
        title={canEdit ? (activation === 'doubleClick' ? 'Double-click to rename' : 'Click to rename') : undefined}
        onClick={activation === 'click' ? start : undefined}
        onDoubleClick={activation === 'doubleClick' ? start : undefined}
      >
        {shown}
      </Tag>
      {canEdit && (
        <button
          type="button"
          className={styles.editButton}
          aria-label={`Rename ${label.toLowerCase()}`}
          onClick={(e) => {
            e.stopPropagation()
            start()
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <Pencil size={13} aria-hidden="true" />
        </button>
      )}
      {error && (
        <span role="alert" className={styles.error}>
          {error}
        </span>
      )}
    </span>
  )
}
