import { AlertTriangle, Check, CheckCircle2, PenLine, RotateCcw, Sparkles, X } from 'lucide-react'
import { useState } from 'react'

import styles from './LocalTax.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type FsEdits, type Money, money, useFsEdit, usePostFsEdits, useUndoFsEdit } from '@/api/localTax'
import { Button } from '@/design-system'

/** A line of the statements the accountant may overwrite (AFIT, 26 Nov 2026) - never a total. Shown as the statements
 * show it (`shown`: signed for display), entered as the positive figure the line stands at; an edited line is marked. */
export function EditableAmount({ taskKey, heading, label, value, shown, edited }: {
  taskKey: string; heading: string; label: string; value: Money; shown: number; edited?: { from: string; by: string }
}) {
  const edit = useFsEdit(taskKey)
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  if (open) {
    const save = () => edit.mutate({ heading, value: text }, { onSuccess: () => setOpen(false) })
    return (
      <span className={styles.figureEdit}>
        <input aria-label={`New figure: ${label}`} inputMode="decimal" value={text} autoFocus onChange={(ev) => setText(ev.target.value)}
          onKeyDown={(ev) => (ev.key === 'Enter' ? save() : ev.key === 'Escape' ? setOpen(false) : undefined)} />
        <Button size="sm" variant="primary" iconOnly aria-label={`Save: ${label}`} disabled={edit.isPending || !text.trim()} onClick={save}><Check size={12} /></Button>
        <Button size="sm" variant="subtle" iconOnly aria-label="Cancel" onClick={() => setOpen(false)}><X size={12} /></Button>
        {edit.isError && <span className={styles.error} role="alert">{extractErrorMessage(edit.error)}</span>}
      </span>
    )
  }
  return (
    <button type="button" className={styles.figure} data-edited={edited ? 'true' : undefined} aria-label={`Edit ${label}: ${money(shown)}`}
      title={edited ? `Edited by ${edited.by} (was ${money(edited.from)})` : 'Edit this figure'}
      onClick={() => (setText(String(Math.round(Number(value ?? 0) * 100) / 100)), setOpen(true))}>
      {money(shown)} <PenLine size={11} aria-hidden="true" />
    </button>
  )
}

/** Where the statement edits stand: out of balance (nothing goes forward until the other side is edited), balanced and
 * ready for Local_Tax_AI to put them in the trial balance, or waiting for that journal's approval. */
export function FsEditsBanner({ taskKey, edits, notes }: { taskKey: string; edits: FsEdits | null | undefined; notes?: string[] }) {
  const post = usePostFsEdits(taskKey)
  const undo = useUndoFsEdit(taskKey)
  if (!edits || (!edits.items.length && !edits.journal)) return null
  const waiting = edits.journal?.status === 'proposed'
  return (
    <div className={edits.balanced ? styles.editsOk : styles.editsOff} role={edits.balanced ? 'status' : 'alert'} aria-label="Statement edits">
      <strong>
        {!edits.balanced ? (
          <><AlertTriangle size={15} aria-hidden="true" /> The edited figures are out of balance by {money(edits.difference)}: edit the other side before you continue.</>
        ) : waiting ? (
          <><CheckCircle2 size={15} aria-hidden="true" /> The edits balance and are in {edits.journal?.ref}, waiting for approval to update the trial balance.</>
        ) : (
          <><CheckCircle2 size={15} aria-hidden="true" /> The edits balance{edits.needs_balance ? '' : ' (income statement only: the net change goes to retained earnings)'}.
            Update the trial balance to keep it in step.</>
        )}
      </strong>
      <ul>
        {edits.items.map((i) => (
          <li key={i.heading}>
            {i.label}: {money(i.from)} → {money(i.to)} <span className={styles.muted}>({Number(i.delta) > 0 ? 'Dr' : 'Cr'} {money(Math.abs(Number(i.delta)))}, {i.by})</span>
            <Button size="sm" variant="subtle" iconOnly aria-label={`Undo the edit: ${i.label}`} onClick={() => undo.mutate(i.heading)}><RotateCcw size={12} /></Button>
          </li>
        ))}
      </ul>
      {notes && notes.length > 0 && waiting && notes.map((n) => <p key={n} className={styles.muted} style={{ margin: 0 }}>{n}</p>)}
      <div className={styles.actions}>
        {edits.can_post && (
          <Button size="sm" variant="primary" disabled={post.isPending} onClick={() => post.mutate(undefined)}>
            <Sparkles size={13} /> {post.isPending ? 'Local_Tax_AI is choosing the accounts…' : 'Update the TB'}
          </Button>
        )}
        {edits.items.length > 0 && <Button size="sm" variant="subtle" onClick={() => undo.mutate(undefined)}>Undo all edits</Button>}
      </div>
      {(post.isError || undo.isError) && <p className={styles.error}>{extractErrorMessage(post.error ?? undo.error)}</p>}
    </div>
  )
}
