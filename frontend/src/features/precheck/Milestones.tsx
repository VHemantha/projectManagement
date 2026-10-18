import { format, parseISO } from 'date-fns'
import { CalendarCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import styles from './AIAssistant.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useMilestones, useStampMilestone } from '@/api/guide'
import { Button } from '@/design-system'

type PersonKind = 'checks' | 'preparation' | 'adjustments'
const PERSON_KINDS: { kind: PersonKind; label: string }[] = [
  { kind: 'checks', label: 'Checks' },
  { kind: 'preparation', label: 'Preparation' },
  { kind: 'adjustments', label: 'Adjustments' },
]

/** When each stage of the task happened: the pre-check, guide and review the AI posted (dated
 * automatically), and the checks, preparation and adjustments a person stamps with their date. */
export function Milestones({ jobKey }: { jobKey: string }) {
  const { data } = useMilestones(jobKey)
  const stamp = useStampMilestone(jobKey)
  const [kind, setKind] = useState<PersonKind | null>(null)
  const [on, setOn] = useState('')
  const [note, setNote] = useState('')
  const milestones = data?.milestones ?? []
  const today = format(new Date(), 'yyyy-MM-dd')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!kind) return
    stamp.mutate({ kind, on: on || today, note: note.trim() }, { onSuccess: () => (setKind(null), setOn(''), setNote('')) })
  }

  return (
    <div className={styles.milestones}>
      <h3 className={styles.subTitle}>
        <CalendarCheck size={14} aria-hidden="true" /> Milestones
      </h3>
      {milestones.length > 0 ? (
        <ol className={styles.timeline} aria-label="Milestones">
          {milestones.map((m) => (
            <li key={m.id}>
              <span className={styles.when}>{format(parseISO(m.on), 'd MMM yyyy')}</span>
              <span className={styles.what}>{m.label}</span>
              <span className={styles.who}>
                {m.auto ? 'by the AI' : ''}
                {m.by && `${m.auto ? ', run by ' : ''}${m.by}`}
                {m.note && ` — ${m.note}`}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.muted}>Nothing dated yet.</p>
      )}
      {kind ? (
        <form className={styles.stampForm} onSubmit={submit} aria-label={`Stamp ${kind}`}>
          <label>
            Date
            <input type="date" value={on || today} max={today} onChange={(e) => setOn(e.target.value)} />
          </label>
          <label className={styles.grow}>
            Note (optional)
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Depreciation and accruals posted" />
          </label>
          <Button type="submit" size="sm" variant="primary" disabled={stamp.isPending}>
            Save
          </Button>
          <Button type="button" size="sm" variant="subtle" onClick={() => setKind(null)}>
            Cancel
          </Button>
        </form>
      ) : (
        <div className={styles.stampRow} role="group" aria-label="Stamp a stage">
          {PERSON_KINDS.map((k) => (
            <button key={k.kind} type="button" className={styles.stamp} onClick={() => setKind(k.kind)}>
              {k.label} done
            </button>
          ))}
        </div>
      )}
      {stamp.isError && <p className={styles.error}>{extractErrorMessage(stamp.error)}</p>}
    </div>
  )
}
