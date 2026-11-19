import { MessagesSquare, RotateCcw } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { AskPanel } from './AskPanel'
import styles from './PrecheckChat.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useAddAgentNote, useRunPrecheck } from '@/api/precheck'
import { Button } from '@/design-system'

const SUGGESTIONS = [
  'Why is the first item on the request list?',
  'How were the Job Snapshot figures worked out?',
  'Which document shows the main income?',
  'What else could explain the change in the largest balance?',
]

/** The Pre-Check Agent's own chat (AFIT design requirements, 16 Nov 2026): questions about this
 * task's pre-check - why an item is there, how a figure was worked out, where the evidence is, and
 * challenges to its assumptions - answered from the task's documents, the Job Snapshot and the
 * findings, with the conversation kept. A correction is kept as a special note for the pre-check
 * (so it is on record, and every later run follows it) and the pre-check runs again; the new
 * result lists the note it considered. Nothing in the accounts changes. */
export function PrecheckChat({ jobKey, running }: { jobKey: string; running: boolean }) {
  const addNote = useAddAgentNote(jobKey)
  const run = useRunPrecheck(jobKey)
  const [correction, setCorrection] = useState('')
  const [done, setDone] = useState(false)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const text = correction.trim()
    if (text.length < 3) return
    addNote.mutate(
      { text, agents: ['precheck'] },
      { onSuccess: () => run.mutate(undefined, { onSuccess: () => (setCorrection(''), setDone(true)) }) },
    )
  }

  return (
    <section className={styles.chat} aria-label="Pre-Check Agent chat">
      <div className={styles.head}>
        <span className={styles.icon} aria-hidden="true">
          <MessagesSquare size={20} />
        </span>
        <div>
          <h3 className={styles.title}>Chat with Pre-Check Agent</h3>
          <p className={styles.lead}>Discuss, clarify or challenge a point. It answers from this job&apos;s documents, the Snapshot and the points.</p>
        </div>
      </div>
      <AskPanel jobKey={jobKey} suggestions={SUGGESTIONS} variant="chat" lead="" placeholder="Type a message to the Pre-Check Agent…" />
      <form className={styles.correct} onSubmit={submit}>
        <label htmlFor="pc-correction" className={styles.correctLabel}>
          <RotateCcw size={14} aria-hidden="true" /> Correct the pre-check and run it again
        </label>
        <textarea
          id="pc-correction"
          value={correction}
          rows={2}
          maxLength={1000}
          placeholder="e.g. The equipment purchase was a lease, not a purchase: there is no invoice to request."
          onChange={(e) => (setCorrection(e.target.value), setDone(false))}
        />
        <div className={styles.correctActions}>
          <span className={styles.muted}>Kept as a special note for the pre-check, so it is on record and every later run follows it.</span>
          <Button type="submit" size="sm" disabled={correction.trim().length < 3 || addNote.isPending || run.isPending || running}>
            {addNote.isPending || run.isPending ? 'Saving…' : 'Save and re-run'}
          </Button>
        </div>
        {done && <p className={styles.done}>Saved. The pre-check is running again; the new result shows the note under “Special notes considered”.</p>}
        {(addNote.isError || run.isError) && <p className={styles.error}>{extractErrorMessage(addNote.error ?? run.error)}</p>}
      </form>
    </section>
  )
}
