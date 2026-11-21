import { format, parseISO } from 'date-fns'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import styles from './EfficiencyTracker.module.css'
import { useEfficiency, useTeamEfficiency } from '@/api/timesheets'
import { Skeleton } from '@/design-system'

const SERIES = [
  { key: 'jobs', label: 'On jobs', color: 'var(--tf-primary)' },
  { key: 'administration', label: 'Administration', color: 'var(--tf-solid-blue)' },
  { key: 'training', label: 'Training', color: 'var(--tf-solid-teal)' },
  { key: 'idle', label: 'Idle', color: 'var(--tf-solid-grey)' },
] as const

const pct = (n: number | null | undefined) => (n == null ? '—' : `${n}%`)

/** The efficiency tracker (AFIT, 21 Nov 2026): each working day's hours against the 7.5 hours expected, on jobs
 * and not; how much of the time expected was logged; and the open jobs' hours against their budget. For a team
 * lead or the CEO, the people they lead too, the most under-logged first. */
export function EfficiencyTracker({ team = false }: { team?: boolean }) {
  const [days, setDays] = useState(10)
  const { data, isLoading, isError } = useEfficiency(days)
  const teamQuery = useTeamEfficiency(days, team)

  return (
    <section className={styles.tracker} aria-label="Efficiency tracker">
      <div className={styles.head}>
        <h2 className={styles.title}>Efficiency tracker</h2>
        <label className={styles.range}>
          <span>Period</span>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={5}>Last week (5 working days)</option>
            <option value={10}>Last two weeks</option>
            <option value={20}>Last four weeks</option>
          </select>
        </label>
      </div>

      {isLoading ? (
        <Skeleton height={220} />
      ) : isError || !data ? (
        <p className={styles.muted}>The efficiency tracker could not be loaded.</p>
      ) : (
        <>
          <dl className={styles.tiles}>
            <div>
              <dt>Hours logged</dt>
              <dd>
                {data.summary.logged.toFixed(1)}h <small>of {data.summary.expected.toFixed(1)}h expected</small>
              </dd>
            </div>
            <div data-tone={(data.summary.efficiency_pct ?? 100) < 100 ? 'warn' : 'good'}>
              <dt>Efficiency</dt>
              <dd>{pct(data.summary.efficiency_pct)}</dd>
            </div>
            <div>
              <dt>On jobs</dt>
              <dd>
                {pct(data.summary.on_jobs_pct)} <small>{data.summary.non_job.toFixed(1)}h not on a job</small>
              </dd>
            </div>
            <div data-tone={data.summary.days_under ? 'warn' : 'good'}>
              <dt>Days under {data.target}h</dt>
              <dd>
                {data.summary.days_under} <small>of {data.summary.working_days}</small>
              </dd>
            </div>
          </dl>

          <div className={styles.chart} role="img"
            aria-label={`Hours logged each working day against ${data.target} hours: ${data.days.map((d) => `${d.date} ${d.logged}h`).join(', ')}`}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.days.map((d) => ({ ...d, day: format(parseISO(d.date), 'EEE d') }))} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} domain={[0, (max: number) => Math.max(9, Math.ceil(max))]} />
                <Tooltip formatter={(v) => `${Number(v).toFixed(2)}h`} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={data.target} stroke="var(--tf-danger)" strokeDasharray="4 4" label={{ value: `${data.target}h`, fontSize: 11, position: 'right' }} />
                {SERIES.map((s) => (
                  <Bar key={s.key} dataKey={s.key} name={s.label} stackId="h" fill={s.color} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          <table className={styles.table} aria-label="Hours by day">
            <thead>
              <tr>
                <th>Day</th><th className={styles.num}>Logged</th><th className={styles.num}>Expected</th><th className={styles.num}>On jobs</th>
                <th className={styles.num}>Not on a job</th><th />
              </tr>
            </thead>
            <tbody>
              {data.days.map((d) => (
                <tr key={d.date} data-under={d.under || undefined}>
                  <th scope="row">{format(parseISO(d.date), 'EEE d MMM')}</th>
                  <td className={styles.num}>{d.logged.toFixed(2)}h</td>
                  <td className={styles.num}>{d.expected ? `${d.expected.toFixed(2)}h` : 'Not a working day'}</td>
                  <td className={styles.num}>{d.jobs.toFixed(2)}h</td>
                  <td className={styles.num}>{(d.idle + d.administration + d.training).toFixed(2)}h</td>
                  <td>{d.under && <span className={styles.under}>Under {data.target}h</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.jobs.length > 0 && (
            <table className={styles.table} aria-label="My open jobs against budget">
              <caption>My open jobs: hours against budget</caption>
              <thead>
                <tr><th>Job</th><th className={styles.num}>Logged</th><th className={styles.num}>Budget</th><th>Used</th></tr>
              </thead>
              <tbody>
                {data.jobs.map((j) => (
                  <tr key={j.key}>
                    <th scope="row">
                      {j.key} <span className={styles.muted}>{j.summary}</span>
                    </th>
                    <td className={styles.num}>{j.logged.toFixed(1)}h</td>
                    <td className={styles.num}>{j.budget ? `${j.budget}h` : '—'}</td>
                    <td>
                      {j.used_pct == null ? '—' : (
                        <span className={styles.meter} data-over={j.used_pct > 100 || undefined}>
                          <span className={styles.track}><span className={styles.fill} style={{ width: `${Math.min(j.used_pct, 100)}%` }} /></span> {j.used_pct}%
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {team && (teamQuery.data?.people.length ?? 0) > 0 && (
        <table className={styles.table} aria-label="Team efficiency">
          <caption>The people you lead (most under-logged first)</caption>
          <thead>
            <tr>
              <th>Person</th><th className={styles.num}>Logged</th><th className={styles.num}>Expected</th><th>Efficiency</th>
              <th className={styles.num}>Days under {teamQuery.data!.target}h</th><th className={styles.num}>Last working day</th>
            </tr>
          </thead>
          <tbody>
            {teamQuery.data!.people.map((p) => (
              <tr key={p.user.id} data-under={p.summary.days_under > 0 || undefined}>
                <th scope="row">{p.user.name}</th>
                <td className={styles.num}>{p.summary.logged.toFixed(1)}h</td>
                <td className={styles.num}>{p.summary.expected.toFixed(1)}h</td>
                <td>
                  <span className={styles.meter} data-over={(p.summary.efficiency_pct ?? 0) < 100 || undefined}>
                    <span className={styles.track}><span className={styles.fill} style={{ width: `${Math.min(p.summary.efficiency_pct ?? 0, 100)}%` }} /></span> {pct(p.summary.efficiency_pct)}
                  </span>
                </td>
                <td className={styles.num}>{p.summary.days_under}</td>
                <td className={styles.num}>
                  {p.last_day ? `${p.last_day.logged.toFixed(1)}h` : '—'}
                  {p.last_day?.under && <span className={styles.under}> under</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
