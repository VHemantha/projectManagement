import { format, parseISO } from 'date-fns'
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock, ListTodo, OctagonAlert, PlayCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, Line, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import dash from '@/features/dashboard/CeoDashboard.module.css'
import styles from './PeopleSnapshot.module.css'
import { DoingNowLine } from './TeamSnapshotPage'
import { type PersonDashboard, type PersonJob, usePersonDashboard } from '@/api/reports'
import { Avatar, IssueKey, Skeleton } from '@/design-system'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'

// The CEO dashboard's validated palette: slot 1 for a single series, the critical red for overdue.
const SERIES_1 = '#2a78d6'
const SERIES_2 = '#eb6834'
const AXIS = { fontSize: 11, stroke: 'var(--tf-text-subtle)', tickLine: false } as const
const TOOLTIP = { cursor: { fill: 'var(--tf-surface-hover)' }, contentStyle: { fontSize: 12, borderRadius: 6 } }

const ddmmyy = (iso: string | null) => (iso ? format(parseISO(iso), 'dd-MM-yy') : '')

function Stat({ label, value, icon, tone }: { label: string; value: ReactNode; icon: ReactNode; tone?: 'critical' | 'warning' | 'good' }) {
  return (
    <div className={dash.stat}>
      <span className={dash.statIcon} data-tone={tone} aria-hidden="true">{icon}</span>
      <span className={dash.statValue}>{value}</span>
      <span className={dash.statLabel}>{label}</span>
    </div>
  )
}

function Card({ title, hint, wide, children }: { title: string; hint?: string; wide?: boolean; children: ReactNode }) {
  return (
    <section className={`${dash.card} ${wide ? dash.wide : ''}`} aria-label={title}>
      <header className={dash.cardHeader}>
        <div>
          <h2 className={dash.cardTitle}>{title}</h2>
          {hint && <p className={dash.hint}>{hint}</p>}
        </div>
      </header>
      {children}
    </section>
  )
}

function JobKey({ job }: { job: Pick<PersonJob, 'key'> }) {
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  return (
    <button type="button" className={styles.keyButton} onClick={() => openIssueModal(job.key)}>
      <IssueKey value={job.key} />
    </button>
  )
}

function OpenJobs({ jobs }: { jobs: PersonJob[] }) {
  if (jobs.length === 0) return <p className={dash.empty}>No open jobs.</p>
  return (
    <div className={dash.tableWrap}>
      <table className={dash.table}>
        <thead>
          <tr>
            <th scope="col">Key</th>
            <th scope="col">Task</th>
            <th scope="col">Stage</th>
            <th scope="col">As</th>
            <th scope="col">Due</th>
            <th scope="col" className={dash.num}>Days overdue</th>
            <th scope="col" className={dash.num}>Hours (actual / budget)</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.key}>
              <td><JobKey job={j} /></td>
              <td>
                {j.sub_workspace && <span className={styles.client}>{j.sub_workspace} · </span>}
                {j.summary}
              </td>
              <td>{j.stage}</td>
              <td>{j.roles.join(', ')}</td>
              <td>{ddmmyy(j.due_date)}</td>
              <td className={`${dash.num} ${j.days_overdue ? dash.over : ''}`}>{j.days_overdue ?? ''}</td>
              <td className={`${dash.num} ${j.budget_hours && j.actual_hours > j.budget_hours ? dash.over : ''}`}>
                {j.actual_hours}
                {j.budget_hours != null ? ` / ${j.budget_hours}` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Body({ data }: { data: PersonDashboard }) {
  const f = data.figures
  const h = data.hours
  const days = h.by_day.map((d) => ({ ...d, label: format(parseISO(d.day), 'EEE d') }))
  const short = h.expected > 0 && h.logged < h.expected
  return (
    <>
      <div className={styles.nowBar}>
        <PlayCircle size={16} aria-hidden="true" />
        <DoingNowLine doing={data.doing_now} />
      </div>

      <div className={dash.stats}>
        <Stat label="Open jobs" value={f.open} icon={<ListTodo size={16} />} />
        <Stat label="In progress" value={f.in_progress} icon={<PlayCircle size={16} />} />
        <Stat label="Overdue" value={f.overdue} icon={<OctagonAlert size={16} />} tone={f.overdue ? 'critical' : undefined} />
        <Stat label="Due in the next 7 days" value={f.due_this_week} icon={<AlertTriangle size={16} />} tone={f.due_this_week ? 'warning' : undefined} />
        <Stat label={`Completed this week (${f.completed_30_days} in 30 days)`} value={f.completed_week} icon={<CheckCircle2 size={16} />} tone="good" />
        <Stat
          label={`Hours this week, of ${h.expected} expected (${h.month}h this month)`}
          value={`${h.logged}h`}
          icon={<Clock size={16} />}
          tone={short ? 'warning' : undefined}
        />
      </div>

      <div className={dash.grid}>
        <Card title="Open jobs" hint="Overdue first, then by due date. Open a key to see the task." wide>
          <OpenJobs jobs={data.open_jobs} />
        </Card>

        <Card title="Open jobs by stage">
          {data.stages.length === 0 ? (
            <p className={dash.empty}>No open jobs.</p>
          ) : (
            <div style={{ height: Math.max(140, 40 + data.stages.length * 30) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.stages} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={6}>
                  <CartesianGrid stroke="var(--tf-border-subtle)" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} {...AXIS} />
                  <YAxis type="category" dataKey="stage" width={130} {...AXIS} />
                  <Tooltip {...TOOLTIP} />
                  <Bar dataKey="tasks" name="Jobs" fill={SERIES_1} radius={[0, 4, 4, 0]} maxBarSize={22} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card title="Hours, last 14 days" hint="Logged each day, against the hours expected from their working week and leave">
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={days} margin={{ left: -16, right: 8 }}>
                <CartesianGrid stroke="var(--tf-border-subtle)" vertical={false} />
                <XAxis dataKey="label" {...AXIS} interval={1} />
                <YAxis {...AXIS} />
                <Tooltip {...TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="hours" name="Logged" fill={SERIES_1} radius={[4, 4, 0, 0]} maxBarSize={28} />
                <Line dataKey="expected" name="Expected" stroke={SERIES_2} strokeWidth={2} dot={false} type="stepAfter" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Today's morning plan">
          {data.morning_plan.length === 0 ? (
            <p className={dash.empty}>No plan set for today.</p>
          ) : (
            <ul className={styles.list}>
              {data.morning_plan.map((g, i) => (
                <li key={i}>
                  <span>
                    {g.text}
                    {g.planned_hours != null && <small> · {g.planned_hours}h today</small>}
                    {g.complete_by && <small> · completion {ddmmyy(g.complete_by)}</small>}
                  </span>
                  <span className={styles.chip} data-tone={g.status === 'achieved' ? 'success' : g.status === 'not_achieved' ? 'danger' : ''}>
                    {g.status_label}
                    {g.lead_check === 'confirmed' ? ' · checked' : g.lead_check === 'not_done' ? ' · lead: not done' : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Completed, last 30 days">
          {data.completed.length === 0 ? (
            <p className={dash.empty}>Nothing completed in the last 30 days.</p>
          ) : (
            <ul className={styles.list}>
              {data.completed.map((j) => (
                <li key={j.key}>
                  <span>
                    <JobKey job={j} /> {j.sub_workspace && `${j.sub_workspace} · `}
                    {j.summary}
                  </span>
                  <small>{ddmmyy(j.completed_at)}</small>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Coordinator follow-ups open">
          {data.follow_ups.length === 0 ? (
            <p className={dash.empty}>Nothing being followed up with them.</p>
          ) : (
            <ul className={styles.list}>
              {data.follow_ups.map((c, i) => (
                <li key={i}>
                  <span>
                    <JobKey job={c} /> {c.matter}
                    {c.due_date && <small> · due {ddmmyy(c.due_date)}</small>}
                    {c.revised_due && <small> · new date {ddmmyy(c.revised_due)}</small>}
                  </span>
                  <span className={styles.chip} data-tone={c.state === 'escalated' ? 'danger' : c.state === 'asked' ? 'warning' : ''}>
                    {c.state_label}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/coordinator/console" className={styles.more}>Open the coordinator console</Link>
        </Card>

        <Card title="Rating" hint={data.rating ? `${ddmmyy(data.rating.period_start)} to ${ddmmyy(data.rating.period_end)}` : undefined}>
          {!data.rating ? (
            <p className={dash.empty}>No rating yet.</p>
          ) : (
            <>
              <p className={styles.rating}>
                <strong>{data.rating.rating}</strong>
                {data.rating.score != null && <span> · {Math.round(data.rating.score)} / 100</span>}
              </p>
              <ul className={styles.list}>
                {data.rating.metrics.map((m) => (
                  <li key={m.key}>
                    <span>{m.label}</span>
                    <small>{m.score == null ? 'no data' : Math.round(m.score)}</small>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title="Latest time logged">
          {data.recent_time.length === 0 ? (
            <p className={dash.empty}>No time logged yet.</p>
          ) : (
            <ul className={styles.list}>
              {data.recent_time.map((e, i) => (
                <li key={i}>
                  <span>
                    {e.key && <JobKey job={e} />} {e.summary || e.description || 'Time not on a task'}
                  </span>
                  <small>
                    {ddmmyy(e.work_date)} · {e.hours}h
                  </small>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  )
}

/** One person's work, for the CEO (AFIT, 5 Nov 2026): what they are doing now, their jobs by stage,
 * what is overdue, what they finished, their hours, today's plan, follow-ups and rating. */
export function PersonSnapshotPage() {
  const { userId } = useParams<{ userId: string }>()
  const isCeo = useAuthStore((s) => s.user?.role === 'ceo')
  const { data, isLoading, isError } = usePersonDashboard(Number(userId))

  if (!isCeo) {
    return (
      <div className={dash.page}>
        <p className={styles.muted}>Only the CEO can see a person&apos;s work snapshot.</p>
      </div>
    )
  }
  return (
    <div className={dash.page}>
      <Link to="/people/work" className={styles.back}>
        <ArrowLeft size={14} aria-hidden="true" /> Team snapshot
      </Link>
      {isLoading ? (
        <Skeleton height={240} />
      ) : isError || !data ? (
        <p className={styles.muted}>This person&apos;s work could not be loaded.</p>
      ) : (
        <>
          <header className={dash.pageHeader}>
            <Avatar name={data.person.display_name} src={data.person.avatar ?? undefined} size={36} userId={data.person.id} />
            <h1 className={dash.pageTitle}>{data.person.display_name}</h1>
            {data.person.job_title && <span className={dash.asOf}>{data.person.job_title}</span>}
            {data.on_leave && <span className={styles.chip} data-tone="warning">On leave today</span>}
            <span className={`${dash.asOf} ${dash.headerActions}`}>As of {format(parseISO(data.as_of), 'd MMM yyyy, HH:mm')}</span>
          </header>
          <Body data={data} />
        </>
      )}
    </div>
  )
}
