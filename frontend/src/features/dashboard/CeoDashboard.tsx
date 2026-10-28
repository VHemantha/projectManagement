import { format, parseISO } from 'date-fns'
import { AlertTriangle, CheckCircle2, Clock, ListTodo, OctagonAlert, Timer } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import styles from './CeoDashboard.module.css'
import { type CeoDashboard as Data, useCeoDashboard } from '@/api/reports'
import { Skeleton } from '@/design-system'

// Validated (dataviz validate_palette.js, light): blue/orange and blue/critical pass CVD and
// normal-vision separation and 3:1 contrast. Single-series charts use slot 1 only.
const SERIES_1 = '#2a78d6'
const SERIES_2 = '#eb6834'
const CRITICAL = '#d03b3b'
const AXIS = { fontSize: 11, stroke: 'var(--tf-text-subtle)', tickLine: false } as const
const GRID = <CartesianGrid stroke="var(--tf-border-subtle)" vertical={false} />
const H_GRID = <CartesianGrid stroke="var(--tf-border-subtle)" horizontal={false} />
const TOOLTIP = { cursor: { fill: 'var(--tf-surface-hover)' }, contentStyle: { fontSize: 12, borderRadius: 6 } }

const week = (iso: string) => format(parseISO(iso), 'd MMM')

/** A chart with a "Table" switch: the same numbers as a table, for screen readers and exact values. */
function ChartCard<Row extends Record<string, unknown>>({ title, hint, rows, columns, height = 240, wide, children }: {
  title: string
  hint?: string
  rows: Row[]
  columns: { key: keyof Row & string; label: string }[]
  height?: number
  wide?: boolean
  children: ReactNode
}) {
  const [table, setTable] = useState(false)
  return (
    <section className={`${styles.card} ${wide ? styles.wide : ''}`} aria-label={title}>
      <header className={styles.cardHeader}>
        <div>
          <h2 className={styles.cardTitle}>{title}</h2>
          {hint && <p className={styles.hint}>{hint}</p>}
        </div>
        <button type="button" className={styles.toggle} aria-pressed={table} onClick={() => setTable((t) => !t)}>
          {table ? 'Chart' : 'Table'}
        </button>
      </header>
      {rows.length === 0 ? (
        <p className={styles.empty}>Nothing to show yet.</p>
      ) : table ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>{columns.map((c) => <td key={c.key}>{String(r[c.key] ?? '')}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">{children as React.ReactElement}</ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

function Stat({ label, value, icon, tone, to }: { label: string; value: ReactNode; icon: ReactNode; tone?: 'critical' | 'warning' | 'good'; to?: string }) {
  const body = (
    <>
      <span className={styles.statIcon} data-tone={tone} aria-hidden="true">{icon}</span>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </>
  )
  return to ? <Link to={to} className={styles.stat}>{body}</Link> : <div className={styles.stat}>{body}</div>
}

/** Horizontal bars of open tasks, on time and overdue, one row per workspace or person. */
function OpenOverdueBars({ rows, nameKey }: { rows: { on_time: number; overdue: number }[]; nameKey: string }) {
  return (
    <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={6}>
      {H_GRID}
      <XAxis type="number" allowDecimals={false} {...AXIS} />
      <YAxis type="category" dataKey={nameKey} width={130} {...AXIS} />
      <Tooltip {...TOOLTIP} />
      <Legend iconType="square" wrapperStyle={{ fontSize: 12 }} />
      <Bar dataKey="on_time" name="On time" stackId="a" fill={SERIES_1} stroke="var(--tf-surface)" strokeWidth={2} />
      <Bar dataKey="overdue" name="Overdue" stackId="a" fill={CRITICAL} stroke="var(--tf-surface)" strokeWidth={2} radius={[0, 4, 4, 0]} />
    </BarChart>
  )
}

function SingleBars<Row>({ rows, nameKey, valueKey, name, vertical }: { rows: Row[]; nameKey: string; valueKey: string; name: string; vertical?: boolean }) {
  return vertical ? (
    <BarChart data={rows} margin={{ left: -16, right: 8 }}>
      {GRID}
      <XAxis dataKey={nameKey} {...AXIS} />
      <YAxis allowDecimals={false} {...AXIS} />
      <Tooltip {...TOOLTIP} />
      <Bar dataKey={valueKey} name={name} fill={SERIES_1} radius={[4, 4, 0, 0]} maxBarSize={48} />
    </BarChart>
  ) : (
    <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={6}>
      {H_GRID}
      <XAxis type="number" allowDecimals={false} {...AXIS} />
      <YAxis type="category" dataKey={nameKey} width={150} {...AXIS} />
      <Tooltip {...TOOLTIP} />
      <Bar dataKey={valueKey} name={name} fill={SERIES_1} radius={[0, 4, 4, 0]} maxBarSize={22} />
    </BarChart>
  )
}

function Dashboard({ data }: { data: Data }) {
  const t = data.totals
  const flow = data.flow.map((w) => ({ ...w, label: week(w.week) }))
  const hours = data.hours.map((w) => ({ ...w, label: week(w.week) }))
  const kept = data.commitments_90_days.kept
  const promised = kept + data.commitments_90_days.missed
  const rowHeight = (n: number) => Math.max(160, 40 + n * 30)

  return (
    <>
      <div className={styles.stats}>
        <Stat label="Open tasks" value={t.open} icon={<ListTodo size={16} />} to="/projects/all-issues" />
        <Stat label="Overdue" value={t.overdue} icon={<OctagonAlert size={16} />} tone={t.overdue ? 'critical' : undefined} />
        <Stat label="Due in the next 7 days" value={t.due_this_week} icon={<AlertTriangle size={16} />} tone={t.due_this_week ? 'warning' : undefined} />
        <Stat label="Completed, last 30 days" value={t.completed_30_days} icon={<CheckCircle2 size={16} />} tone="good" />
        <Stat label="Hours logged this month" value={`${t.hours_this_month}h`} icon={<Clock size={16} />} to="/timesheets/reports" />
        <Stat label="Timesheets to approve" value={t.timesheets_to_approve} icon={<Timer size={16} />} to="/timesheets/review" />
      </div>

      <div className={styles.grid}>
        <ChartCard title="Tasks by stage" hint="Every task not archived" rows={data.stages}
          columns={[{ key: 'stage', label: 'Stage' }, { key: 'tasks', label: 'Tasks' }]} height={rowHeight(data.stages.length)}>
          <SingleBars rows={data.stages} nameKey="stage" valueKey="tasks" name="Tasks" />
        </ChartCard>

        <ChartCard title="Tasks created and completed" hint="Per week, last 12 weeks" rows={flow}
          columns={[{ key: 'label', label: 'Week of' }, { key: 'created', label: 'Created' }, { key: 'completed', label: 'Completed' }]}>
          <LineChart data={flow} margin={{ left: -16, right: 16, top: 8 }}>
            {GRID}
            <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" />
            <YAxis allowDecimals={false} {...AXIS} />
            <Tooltip cursor={{ stroke: 'var(--tf-border)' }} contentStyle={TOOLTIP.contentStyle} />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="created" name="Created" stroke={SERIES_1} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: 'var(--tf-surface)' }} />
            <Line type="monotone" dataKey="completed" name="Completed" stroke={SERIES_2} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: 'var(--tf-surface)' }} />
          </LineChart>
        </ChartCard>

        <ChartCard title="Open tasks by workspace" hint="On time and overdue" rows={data.workspaces}
          columns={[{ key: 'workspace', label: 'Workspace' }, { key: 'open', label: 'Open' }, { key: 'overdue', label: 'Overdue' }, { key: 'completed_30', label: 'Completed (30 days)' }]}
          height={rowHeight(data.workspaces.length) + 24}>
          <OpenOverdueBars rows={data.workspaces} nameKey="workspace" />
        </ChartCard>

        <ChartCard title="Team Lead workload" hint="Open tasks per Team Lead (top 12)" rows={data.workload}
          columns={[{ key: 'person', label: 'Team Lead' }, { key: 'open', label: 'Open' }, { key: 'overdue', label: 'Overdue' }]}
          height={rowHeight(data.workload.length) + 24}>
          <OpenOverdueBars rows={data.workload} nameKey="person" />
        </ChartCard>

        <ChartCard title="Hours logged" hint="Per week, last 12 weeks" rows={hours}
          columns={[{ key: 'label', label: 'Week of' }, { key: 'billable', label: 'Billable (h)' }, { key: 'non_billable', label: 'Non-billable (h)' }]}>
          <BarChart data={hours} margin={{ left: -16, right: 8 }}>
            {GRID}
            <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" />
            <YAxis {...AXIS} />
            <Tooltip {...TOOLTIP} />
            <Legend iconType="square" wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="billable" name="Billable" stackId="h" fill={SERIES_1} stroke="var(--tf-surface)" strokeWidth={2} maxBarSize={36} />
            <Bar dataKey="non_billable" name="Non-billable" stackId="h" fill={SERIES_2} stroke="var(--tf-surface)" strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={36} />
          </BarChart>
        </ChartCard>

        <ChartCard title="Open tasks by priority" rows={data.priorities}
          columns={[{ key: 'priority', label: 'Priority' }, { key: 'tasks', label: 'Open tasks' }]}>
          <SingleBars rows={data.priorities} nameKey="priority" valueKey="tasks" name="Open tasks" vertical />
        </ChartCard>

        <ChartCard title="Busiest sub-workspaces" hint="Open tasks (top 10)" rows={data.sub_workspaces}
          columns={[{ key: 'sub_workspace', label: 'Sub-workspace' }, { key: 'open', label: 'Open tasks' }]}
          height={rowHeight(data.sub_workspaces.length)}>
          <SingleBars rows={data.sub_workspaces} nameKey="sub_workspace" valueKey="open" name="Open tasks" />
        </ChartCard>

        <ChartCard title="AI pre-checks" hint="Runs in the last 30 days, by result" rows={data.prechecks}
          columns={[{ key: 'result', label: 'Result' }, { key: 'runs', label: 'Runs' }]}
          height={rowHeight(data.prechecks.length)}>
          <SingleBars rows={data.prechecks} nameKey="result" valueKey="runs" name="Runs" />
        </ChartCard>

        <section className={styles.card} aria-label="Coordinator follow-ups">
          <header className={styles.cardHeader}>
            <div>
              <h2 className={styles.cardTitle}>Coordinator follow-ups</h2>
              <p className={styles.hint}>Open cases now; revised dates over the last 90 days</p>
            </div>
            <Link to="/coordinator/console" className={styles.toggle}>Open console</Link>
          </header>
          <div className={styles.miniStats}>
            <Stat label="Waiting for a reply" value={data.follow_ups.waiting} icon={<Clock size={16} />} />
            <Stat label="Answered" value={data.follow_ups.answered} icon={<CheckCircle2 size={16} />} />
            <Stat label="Escalated" value={data.follow_ups.escalated} icon={<OctagonAlert size={16} />} tone={data.follow_ups.escalated ? 'critical' : undefined} />
            <Stat
              label={promised ? `Revised dates kept (${kept} of ${promised})` : 'Revised dates kept'}
              value={promised ? `${Math.round((kept / promised) * 100)}%` : '—'}
              icon={<CheckCircle2 size={16} />}
            />
          </div>
          <p className={styles.leave}>
            <strong>On leave today:</strong> {data.on_leave_today.length ? data.on_leave_today.join(', ') : 'no one'}
          </p>
        </section>

        <section className={`${styles.card} ${styles.wide}`} aria-label="Over budget">
          <header className={styles.cardHeader}>
            <div>
              <h2 className={styles.cardTitle}>Over budget</h2>
              <p className={styles.hint}>Open tasks whose logged time is past their budgeted hours</p>
            </div>
          </header>
          {data.over_budget.length === 0 ? (
            <p className={styles.empty}>No open task is over its budget.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr><th>Task</th><th>Job Name</th><th>Team Lead</th><th className={styles.num}>Budget</th><th className={styles.num}>Logged</th><th className={styles.num}>Over by</th></tr>
                </thead>
                <tbody>
                  {data.over_budget.map((r) => (
                    <tr key={r.key}>
                      <td>{r.key}</td>
                      <td>{r.summary}</td>
                      <td>{r.team_lead || '—'}</td>
                      <td className={styles.num}>{r.budgeted}h</td>
                      <td className={styles.num}>{r.actual}h</td>
                      <td className={`${styles.num} ${styles.over}`}>{Number((r.actual - r.budgeted).toFixed(1))}h</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  )
}

/** The CEO's home page: the whole organisation at a glance (AFIT, 28 Oct 2026). */
export function CeoDashboard() {
  const { data, isLoading, isError } = useCeoDashboard()
  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Organisation overview</h1>
        {data && <span className={styles.asOf}>Updated {format(parseISO(data.as_of), 'EEE d MMM, h:mm a')}</span>}
      </header>
      {isLoading ? (
        <Skeleton height={320} />
      ) : isError || !data ? (
        <p className={styles.empty}>The overview could not be loaded. Refresh to try again.</p>
      ) : (
        <Dashboard data={data} />
      )}
    </div>
  )
}
