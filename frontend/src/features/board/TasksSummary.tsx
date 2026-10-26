import { addDays, format, parseISO, startOfDay } from 'date-fns'
import { useMemo } from 'react'

import styles from './TasksSummary.module.css'
import type { IssueListItem } from '@/api/types'

interface Row {
  label: string
  open: number
  done: number
  overdue: number
  logged: number
  budgeted: number
}

const hours = (h: number) => `${h.toFixed(1)}h`

function tally(issues: IssueListItem[], keyOf: (i: IssueListItem) => string, today: Date): Row[] {
  const rows = new Map<string, Row>()
  for (const i of issues) {
    const label = keyOf(i)
    const r = rows.get(label) ?? { label, open: 0, done: 0, overdue: 0, logged: 0, budgeted: 0 }
    const done = i.status.category === 'done'
    if (done) r.done += 1
    else r.open += 1
    if (!done && i.due_date && parseISO(i.due_date) < today) r.overdue += 1
    r.logged += i.actual_hours ?? 0
    r.budgeted += i.budgeted_hours ?? 0
    rows.set(label, r)
  }
  return [...rows.values()].sort((a, b) => b.open + b.done - (a.open + a.done) || a.label.localeCompare(b.label))
}

/** A summary report of the tasks in view (the same workspace / sub-workspace filters as the
 * Kanban): what is open, overdue and due soon, hours logged against the budget, and the same by
 * status, by person and by group. */
export function TasksSummary({ issues, isLoading }: { issues: IssueListItem[]; isLoading?: boolean }) {
  const todayKey = format(new Date(), 'yyyy-MM-dd')
  const today = useMemo(() => startOfDay(parseISO(todayKey)), [todayKey])
  const data = useMemo(() => {
    const open = issues.filter((i) => i.status.category !== 'done')
    const weekAhead = addDays(today, 7)
    return {
      open: open.length,
      done: issues.length - open.length,
      overdue: open.filter((i) => i.due_date && parseISO(i.due_date) < today).length,
      dueSoon: open.filter((i) => i.due_date && parseISO(i.due_date) >= today && parseISO(i.due_date) <= weekAhead).length,
      logged: issues.reduce((s, i) => s + (i.actual_hours ?? 0), 0),
      budgeted: issues.reduce((s, i) => s + (i.budgeted_hours ?? 0), 0),
      overBudget: issues.filter((i) => i.budgeted_hours && i.actual_hours > i.budgeted_hours).length,
      unassigned: open.filter((i) => !i.assignee).length,
      byStatus: tally(issues, (i) => i.status.name, today),
      byPerson: tally(issues, (i) => i.assignee?.display_name ?? 'Unassigned', today),
      byGroup: tally(issues, (i) => i.group || 'No group', today),
    }
  }, [issues, today])

  if (isLoading) return <p className={styles.muted}>Loading…</p>
  if (!issues.length) return <p className={styles.muted}>No tasks to summarise.</p>
  const pct = data.budgeted ? Math.round((data.logged / data.budgeted) * 100) : null

  return (
    <div className={styles.summary}>
      <div className={styles.figures} role="list" aria-label="Totals">
        <Figure value={data.open} label="Open" />
        <Figure value={data.done} label="Done" />
        <Figure value={data.overdue} label="Overdue" tone={data.overdue ? 'danger' : undefined} />
        <Figure value={data.dueSoon} label="Due in the next 7 days" />
        <Figure value={`${hours(data.logged)} / ${hours(data.budgeted)}`} label={`Logged / budgeted${pct !== null ? ` (${pct}%)` : ''}`} />
        <Figure value={data.overBudget} label="Over budget" tone={data.overBudget ? 'warning' : undefined} />
        <Figure value={data.unassigned} label="Open with nobody assigned" />
      </div>
      <p className={styles.muted}>As at {format(today, 'd MMM yyyy')}.</p>
      <Breakdown title="By status" rows={data.byStatus} />
      <Breakdown title="By person" rows={data.byPerson} />
      {data.byGroup.some((r) => r.label !== 'No group') && <Breakdown title="By group" rows={data.byGroup} />}
    </div>
  )
}

function Figure({ value, label, tone }: { value: number | string; label: string; tone?: 'danger' | 'warning' }) {
  return (
    <div className={styles.figure} role="listitem" data-tone={tone}>
      <div className={styles.value}>{value}</div>
      <div className={styles.label}>{label}</div>
    </div>
  )
}

function Breakdown({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h3 className={styles.title}>{title}</h3>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col" />
            <th scope="col">Open</th>
            <th scope="col">Overdue</th>
            <th scope="col">Done</th>
            <th scope="col">Logged</th>
            <th scope="col">Budgeted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              <td>{r.open}</td>
              <td data-tone={r.overdue ? 'danger' : undefined}>{r.overdue}</td>
              <td>{r.done}</td>
              <td>{hours(r.logged)}</td>
              <td>{r.budgeted ? hours(r.budgeted) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
