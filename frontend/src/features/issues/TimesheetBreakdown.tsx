import { format, parseISO } from 'date-fns'
import { type ReactNode, useMemo, useState } from 'react'

import styles from './TimesheetBreakdown.module.css'
import { useTimeEntries } from '@/api/timesheets'
import type { TimeEntry } from '@/api/types'
import { Dialog, DialogContent, Skeleton } from '@/design-system'

const hours = (seconds: number) => `${Number((seconds / 3600).toFixed(2))}h`

/** The task's actual time, entry by entry: who logged it, when, how long and for what. */
export function TimesheetBreakdownDialog({ issueId, issueKey, title, open, onOpenChange }: {
  issueId: number
  issueKey: string
  title: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: entries, isLoading } = useTimeEntries({ issue: issueId, page_size: 500 }, open)
  const people = useMemo(() => {
    const byPerson = new Map<number, { name: string; total: number; entries: TimeEntry[] }>()
    for (const e of entries ?? []) {
      const row = byPerson.get(e.user.id) ?? { name: e.user.display_name, total: 0, entries: [] }
      row.total += e.duration_seconds
      row.entries.push(e)
      byPerson.set(e.user.id, row)
    }
    return [...byPerson.values()].sort((a, b) => b.total - a.total)
  }, [entries])
  const total = people.reduce((s, p) => s + p.total, 0)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={`Timesheet breakup — ${issueKey}`} maxWidth={640}>
        <p className={styles.lead}>{title}</p>
        {isLoading ? (
          <Skeleton height={60} />
        ) : people.length === 0 ? (
          <p className={styles.muted}>No time has been logged on this task yet.</p>
        ) : (
          <>
            <p className={styles.total}>
              <strong>{hours(total)}</strong> logged by {people.length} {people.length === 1 ? 'person' : 'people'}
            </p>
            {people.map((p) => (
              <section key={p.name} className={styles.person} aria-label={p.name}>
                <h3 className={styles.name}>
                  {p.name} <span className={styles.hours}>{hours(p.total)}</span>
                </h3>
                <table className={styles.table}>
                  <tbody>
                    {p.entries.map((e) => (
                      <tr key={e.id}>
                        <td className={styles.date}>{format(parseISO(e.work_date), 'EEE d MMM yyyy')}</td>
                        <td className={styles.num}>{hours(e.duration_seconds)}</td>
                        <td>
                          {e.description || <span className={styles.muted}>No description</span>}
                          {!e.is_billable && <span className={styles.tag}>Non-billable</span>}
                          {e.is_running && <span className={styles.tag}>Running</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** A button that opens the breakup. Inside a Kanban card it neither drags nor opens the card. */
export function TimesheetBreakdownLink({ issueId, issueKey, title, children, label }: {
  issueId: number
  issueKey: string
  title: string
  children: ReactNode
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation()
  return (
    <span onClick={stop} onPointerDown={stop} onKeyDown={stop}>
      <button type="button" className={styles.link} aria-label={label ?? `Timesheet breakup for ${issueKey}`} onClick={() => setOpen(true)}>
        {children}
      </button>
      {open && <TimesheetBreakdownDialog issueId={issueId} issueKey={issueKey} title={title} open={open} onOpenChange={setOpen} />}
    </span>
  )
}
