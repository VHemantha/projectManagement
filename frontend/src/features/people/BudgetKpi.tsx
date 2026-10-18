import { format, subDays } from 'date-fns'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './BudgetKpi.module.css'
import { usePersonKpi } from '@/api/guide'

const PERIODS = [
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
  { days: 365, label: '12 months' },
] as const

const hours = (h: number) => `${h.toFixed(1)}h`

/** The person's budget KPI: of the tasks assigned to them that had a budgeted time and were
 * finished in the period, how many came in within budget, and the hours they logged against the
 * hours budgeted. Open tasks already over budget are shown too. */
export function BudgetKpi({ userId }: { userId: number }) {
  const [days, setDays] = useState<number>(90)
  const to = format(new Date(), 'yyyy-MM-dd')
  const from = format(subDays(new Date(), days), 'yyyy-MM-dd')
  const { data, isLoading, isError } = usePersonKpi(userId, from, to)
  const over = data?.tasks.filter((t) => !t.within_budget) ?? []

  return (
    <section className={styles.card} aria-label="Budget vs actual">
      <div className={styles.head}>
        <h2 className={styles.title}>Budget vs actual</h2>
        <div className={styles.periods} role="group" aria-label="Period">
          {PERIODS.map((p) => (
            <button key={p.days} type="button" aria-pressed={days === p.days} className={styles.period} onClick={() => setDays(p.days)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {isLoading ? (
        <p className={styles.muted}>Loading…</p>
      ) : isError || !data ? (
        <p className={styles.muted}>The KPI could not be loaded.</p>
      ) : data.finished.tasks === 0 && data.open.tasks === 0 ? (
        <p className={styles.muted}>No budgeted tasks in this period.</p>
      ) : (
        <>
          <div className={styles.figures}>
            <Figure value={data.finished.pct_within_budget === null ? '—' : `${data.finished.pct_within_budget}%`}
              label={`Finished within budget (${data.finished.within_budget} of ${data.finished.tasks})`} />
            <Figure value={`${hours(data.finished.actual_hours)} / ${hours(data.finished.budgeted_hours)}`} label="Logged / budgeted on finished tasks" />
            <Figure value={data.finished.efficiency_pct === null ? '—' : `${data.finished.efficiency_pct}%`} label="Efficiency (budget ÷ actual)" />
            <Figure value={`${data.open.over_budget_already}`} label={`Open tasks already over budget (of ${data.open.tasks})`} />
          </div>
          {over.length > 0 && (
            <table className={styles.table}>
              <caption className={styles.caption}>Over budget</caption>
              <thead>
                <tr>
                  <th scope="col">Task</th>
                  <th scope="col">Budgeted</th>
                  <th scope="col">Logged</th>
                  <th scope="col">Over by</th>
                </tr>
              </thead>
              <tbody>
                {over.map((t) => (
                  <tr key={t.key}>
                    <td>
                      <Link to={`/projects/${t.project}/issues/${t.key}`}>{t.key}</Link> {t.summary}
                      {!t.done && <span className={styles.open}> open</span>}
                    </td>
                    <td>{hours(t.budgeted_hours)}</td>
                    <td>{hours(t.actual_hours)}</td>
                    <td>{hours(Math.abs(t.variance_hours))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  )
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className={styles.figure}>
      <div className={styles.value}>{value}</div>
      <div className={styles.label}>{label}</div>
    </div>
  )
}
