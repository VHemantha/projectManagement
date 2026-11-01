import { format, parseISO } from 'date-fns'
import { Fragment, useState } from 'react'

import styles from './Coordinator.module.css'
import { type PersonRating, useRatings } from '@/api/coordinator'
import { Skeleton } from '@/design-system'

const RATING_TONE: Record<string, string> = { Excellent: 'success', Good: 'success', 'Needs improvement': 'warning', 'At risk': 'danger' }
const PERIODS = [30, 90, 180, 365]

function change(r: PersonRating) {
  if (r.score == null || r.previous_score == null) return null
  const diff = Math.round((r.score - r.previous_score) * 10) / 10
  if (diff === 0) return <small>No change since last week</small>
  return <small>{diff > 0 ? `Up ${diff}` : `Down ${Math.abs(diff)}`} since last week</small>
}

/** One KPI as a bar from 0 to 100, with the count behind it. A KPI left out says why. */
function MetricRow({ m }: { m: PersonRating['metrics'][number] }) {
  return (
    <li className={styles.kpi} data-counted={m.counted}>
      <span className={styles.kpiLabel}>
        {m.label} <small>(weight {m.weight})</small>
      </span>
      <span className={styles.kpiBar} aria-hidden="true">
        <span style={{ width: `${m.score ?? 0}%` }} />
      </span>
      <span className={styles.kpiScore}>{m.score == null ? '—' : m.score}</span>
      <small className={styles.kpiDetail}>{m.counted ? m.detail : `${m.detail}. ${m.note}.`}</small>
    </li>
  )
}

/** Employee ratings: each person's KPIs and rating, as the coordinator works them out (CEO only). */
export function RatingsTab() {
  const [days, setDays] = useState<number | undefined>()
  const [open, setOpen] = useState<number | null>(null)
  const { data, isLoading, isError } = useRatings(days)
  if (isLoading) return <Skeleton height={120} />
  if (isError || !data) return <p className={styles.muted}>The ratings could not be loaded.</p>
  const totalWeight = data.formula.weights.reduce((s, w) => s + w.weight, 0)

  return (
    <div className={styles.stack}>
      <section className={styles.card} aria-label="How the rating is worked out">
        <h2 className={styles.cardTitle}>How the rating is worked out</h2>
        <p className={styles.muted}>
          Each KPI is a share from 0 to 100 over the period, from the job records, for the tasks the person is the Accountant on. The rating
          is their weighted average: Σ (weight × KPI) ÷ Σ weight, over the KPIs with at least {data.formula.min_items} items to go on (5
          working days for timesheets). With under {data.formula.min_coverage_pct}% of the weight counted, the rating says "Not enough data".
        </p>
        <ul className={styles.formula}>
          {data.formula.weights.map((w) => (
            <li key={w.key}>
              {w.label}: <strong>{w.weight}</strong>
              {totalWeight > 0 && <small> ({Math.round((w.weight / totalWeight) * 100)}%)</small>}
            </li>
          ))}
        </ul>
        <p className={styles.muted}>
          Bands: {data.formula.bands.map((b) => `${b.label} ${b.from > 0 ? `${b.from}+` : `below ${data.formula.bands[data.formula.bands.length - 2]?.from}`}`).join(' · ')}.
          Change the weights and the period under Rules. The coordinator keeps everyone's rating each Monday and sends you the weekly
          report; only you see them.
        </p>
      </section>

      <section className={styles.card} aria-label="Ratings">
        <div className={styles.row}>
          <h2 className={styles.cardTitle}>
            Ratings, {format(parseISO(data.period.from), 'd MMM')} – {format(parseISO(data.period.to), 'd MMM yyyy')}
          </h2>
          <label className={styles.inline}>
            Period
            <select aria-label="Period" value={days ?? ''} onChange={(e) => setDays(e.target.value ? Number(e.target.value) : undefined)}>
              <option value="">As the rule says</option>
              {PERIODS.map((d) => (
                <option key={d} value={d}>
                  Last {d} days
                </option>
              ))}
            </select>
          </label>
        </div>
        {data.people.length === 0 ? (
          <p className={styles.muted}>No one has had tasks to rate yet.</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Person</th>
                  <th scope="col">Rating</th>
                  {data.formula.weights.map((w) => (
                    <th key={w.key} scope="col" title={w.label}>
                      {w.label}
                    </th>
                  ))}
                  <th scope="col">Reasons given</th>
                </tr>
              </thead>
              <tbody>
                {data.people.map((r) => {
                  const shown = open === r.person.id
                  return (
                    <Fragment key={r.person.id}>
                      <tr>
                        <td>
                          <button type="button" className={styles.linkButton} aria-expanded={shown} onClick={() => setOpen(shown ? null : r.person.id)}>
                            {r.person.display_name}
                          </button>
                          <small>{r.finished_tasks} finished tasks</small>
                        </td>
                        <td>
                          <strong className={styles.score}>{r.score ?? '—'}</strong>{' '}
                          <span className={styles.chip} data-tone={RATING_TONE[r.rating] ?? ''}>
                            {r.rating}
                          </span>
                          {change(r)}
                        </td>
                        {r.metrics.map((m) => (
                          <td key={m.key} className={m.counted ? undefined : styles.muted} title={m.counted ? m.detail : `${m.detail}. ${m.note}.`}>
                            {m.score == null ? '—' : m.score}
                            <small>n = {m.n}</small>
                          </td>
                        ))}
                        <td>
                          {Object.keys(r.reasons).length === 0
                            ? '—'
                            : Object.entries(r.reasons).map(([cause, n]) => (
                                <small key={cause}>
                                  {cause}: {n}
                                </small>
                              ))}
                        </td>
                      </tr>
                      {shown && (
                        <tr>
                          <td colSpan={data.formula.weights.length + 3}>
                            <ul className={styles.kpis} aria-label={`${r.person.display_name}'s KPIs`}>
                              {r.metrics.map((m) => (
                                <MetricRow key={m.key} m={m} />
                              ))}
                            </ul>
                            {r.history.length > 0 && (
                              <p className={styles.muted}>
                                Weekly ratings:{' '}
                                {r.history.map((h) => `${format(parseISO(h.date), 'd MMM')} ${h.score ?? '—'}`).join(' · ')}
                              </p>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
