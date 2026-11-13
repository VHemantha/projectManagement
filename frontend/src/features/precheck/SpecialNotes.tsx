import { Check, NotebookPen, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { NOTE_AGENTS } from './noteAgents'
import styles from './SpecialNotes.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type NoteAgent, type NoteConsidered, useAddAgentNote, useAgentNotes, useRemoveAgentNote } from '@/api/precheck'
import { Button } from '@/design-system'

const LABEL = Object.fromEntries(NOTE_AGENTS.map((a) => [a.value, a.label])) as Record<NoteAgent, string>

/** Special notes to the AI agents on this task (AFIT, 13 Nov 2026): "the client sold the rental in June,
 * treat it as the year of sale". Every later run of the agents a note names (none ticked: all of them)
 * follows it when it decides and writes, and lists it with its result. */
export function SpecialNotes({ jobKey }: { jobKey: string }) {
  const { data } = useAgentNotes(jobKey)
  const add = useAddAgentNote(jobKey)
  const remove = useRemoveAgentNote(jobKey)
  const [text, setText] = useState('')
  const [agents, setAgents] = useState<NoteAgent[]>([])
  const notes = data?.notes ?? []
  const full = data ? notes.length >= data.max : false

  const toggle = (a: NoteAgent) => setAgents((now) => (now.includes(a) ? now.filter((x) => x !== a) : [...now, a]))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim().length < 3) return
    add.mutate({ text: text.trim(), agents }, { onSuccess: () => (setText(''), setAgents([])) })
  }

  return (
    <section className={styles.notes} aria-label="Special notes for the AI">
      <div className={styles.head}>
        <NotebookPen size={18} aria-hidden="true" />
        <div>
          <h3 className={styles.title}>Special notes for the AI</h3>
          <p className={styles.purpose}>
            Tell the agents anything they should know or do on this task. They follow these notes when they decide and write their
            results, from their next run.
          </p>
        </div>
      </div>

      {notes.length > 0 && (
        <ul className={styles.list}>
          {notes.map((n) => (
            <li key={n.id} className={styles.note}>
              <p className={styles.text}>{n.text}</p>
              <div className={styles.meta}>
                <span className={styles.for}>
                  For: {n.agents.length ? n.agents.map((a) => LABEL[a]).join(', ') : 'all agents'}
                </span>
                {n.by && <span>· {n.by}</span>}
                {n.can_edit && (
                  <button
                    type="button"
                    className={styles.remove}
                    aria-label={`Remove note: ${n.text}`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(n.id)}
                  >
                    <Trash2 size={13} aria-hidden="true" /> Remove
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {full ? (
        <p className={styles.muted}>This task has the most notes it can hold. Remove one to add another.</p>
      ) : (
        <form className={styles.form} onSubmit={submit}>
          <textarea
            aria-label="New note for the AI"
            placeholder="e.g. The client sold 12 Kauri Street in June 2025: treat this year as the year of sale."
            value={text}
            maxLength={1000}
            rows={2}
            onChange={(e) => setText(e.target.value)}
          />
          <fieldset className={styles.agents} aria-label="Agents the note is for">
            <legend>For</legend>
            {NOTE_AGENTS.map((a) => (
              <label key={a.value} className={styles.agent}>
                <input type="checkbox" checked={agents.includes(a.value)} onChange={() => toggle(a.value)} /> {a.label}
              </label>
            ))}
            <span className={styles.hint}>{agents.length ? '' : 'None ticked: every agent.'}</span>
          </fieldset>
          <div className={styles.actions}>
            <Button type="submit" size="sm" disabled={text.trim().length < 3 || add.isPending}>
              {add.isPending ? 'Adding…' : 'Add note'}
            </Button>
          </div>
        </form>
      )}
      {(add.isError || remove.isError) && <p className={styles.error}>{extractErrorMessage(add.error ?? remove.error)}</p>}
    </section>
  )
}

/** On a result: the special notes the agent was given, marked where it used one. */
export function NotesConsidered({ notes }: { notes?: NoteConsidered[] }) {
  if (!notes?.length) return null
  return (
    <div className={styles.considered} role="group" aria-label="Special notes considered">
      <span className={styles.consideredTitle}>Special notes considered</span>
      <ul>
        {notes.map((n) => (
          <li key={n.id}>
            {n.text}
            {n.by && <span className={styles.muted}> · {n.by}</span>}
            {n.cited && (
              <span className={styles.used}>
                <Check size={12} aria-hidden="true" /> Used in this result
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
