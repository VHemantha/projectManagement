import { format, startOfMonth } from 'date-fns'
import { ArrowLeft } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router-dom'

import styles from './TimeReportsPage.module.css'
import { useProjects } from '@/api/projects'
import { type IssueBudgetRow, type ProjectBudgetRow, useBudgetVsActual } from '@/api/reports'
import { useTimeEntries, type TimeEntryQueryParams } from '@/api/timesheets'
import type { TimeEntry } from '@/api/types'
import { useUsers } from '@/api/users'
import { IssueKey, Skeleton } from '@/design-system'
import { type DataColumn, DataTable } from '@/features/tables/DataTable'

function pctColor(pct: number | null) {
  if (pct == null) return 'var(--tf-text)'
  if (pct > 100) return 'var(--tf-danger)'
  if (pct >= 80) return 'var(--tf-warning)'
  return 'var(--tf-text)'
}

const hours = (value: number | null | undefined, digits = 1) => (value == null ? null : Number(value.toFixed(digits)))
const money = (currency: string, value: string | number | null) =>
  value == null ? '—' : `${currency} ${Number(value).toLocaleString()}`
const overBudget = (variance: number | null) =>
  variance != null && variance > 0 ? { color: 'var(--tf-danger)' } : undefined

const PROJECT_COLUMNS: DataColumn<ProjectBudgetRow>[] = [
  {
    id: 'project',
    label: 'Project',
    required: true,
    size: 240,
    value: (r) => r.project_name,
    cell: (r) => (
      <>
        {r.project_name} <span style={{ color: 'var(--tf-text-subtle)' }}>({r.project_key})</span>
      </>
    ),
  },
  { id: 'client', label: 'Sub-workspace', value: (r) => r.client, defaultHidden: true },
  { id: 'team', label: 'Team', value: (r) => r.team, defaultHidden: true },
  { id: 'lead', label: 'Lead', value: (r) => r.lead, defaultHidden: true },
  { id: 'job_count', label: 'Tasks', value: (r) => r.job_count, numeric: true, defaultHidden: true },
  { id: 'open_jobs', label: 'Open tasks', value: (r) => r.open_jobs, numeric: true, defaultHidden: true },
  { id: 'done_jobs', label: 'Done tasks', value: (r) => r.done_jobs, numeric: true, defaultHidden: true },
  { id: 'archived_jobs', label: 'Archived tasks', value: (r) => r.archived_jobs, numeric: true, defaultHidden: true },
  { id: 'budgeted', label: 'Budgeted (h)', value: (r) => r.budgeted_hours, numeric: true },
  { id: 'actual', label: 'Actual (h)', value: (r) => hours(r.actual_hours), numeric: true },
  {
    id: 'variance',
    label: 'Variance (h)',
    numeric: true,
    value: (r) => hours(r.variance_hours),
    cell: (r) => <span style={overBudget(r.variance_hours)}>{hours(r.variance_hours) ?? '—'}</span>,
  },
  {
    id: 'pct',
    label: '% of budget',
    numeric: true,
    value: (r) => r.pct_complete,
    cell: (r) => (
      <span style={{ color: pctColor(r.pct_complete), fontWeight: 600 }}>
        {r.pct_complete != null ? `${r.pct_complete}%` : '—'}
      </span>
    ),
  },
  { id: 'job_value', label: 'Project value', numeric: true, value: (r) => (r.job_value == null ? null : Number(r.job_value)), cell: (r) => money(r.job_value_currency, r.job_value) },
  { id: 'cost', label: 'Effective cost', numeric: true, value: (r) => Number(r.effective_cost), cell: (r) => money(r.job_value_currency, r.effective_cost) },
  {
    id: 'margin',
    label: 'Margin',
    numeric: true,
    value: (r) => (r.margin == null ? null : Number(r.margin)),
    cell: (r) => (
      <span style={r.margin != null && Number(r.margin) < 0 ? { color: 'var(--tf-danger)' } : undefined}>
        {money(r.job_value_currency, r.margin)}
      </span>
    ),
  },
]

const JOB_COLUMNS: DataColumn<IssueBudgetRow>[] = [
  { id: 'key', label: 'Task', required: true, size: 120, value: (r) => r.issue_key, cell: (r) => <IssueKey value={r.issue_key} /> },
  { id: 'summary', label: 'Summary', size: 260, value: (r) => r.summary },
  { id: 'type', label: 'Type', value: (r) => r.issue_type, defaultHidden: true },
  { id: 'status', label: 'Status', value: (r) => r.status, defaultHidden: true },
  { id: 'assignee', label: 'Assignee', value: (r) => r.assignee, defaultHidden: true },
  { id: 'due', label: 'Due', value: (r) => r.due_date, defaultHidden: true },
  { id: 'archived', label: 'Archived', value: (r) => r.is_archived, defaultHidden: true },
  { id: 'budgeted', label: 'Budgeted (h)', value: (r) => r.budgeted_hours, numeric: true },
  { id: 'actual', label: 'Actual (h)', value: (r) => hours(r.actual_hours), numeric: true },
  {
    id: 'variance',
    label: 'Variance (h)',
    numeric: true,
    value: (r) => hours(r.variance_hours),
    cell: (r) => <span style={overBudget(r.variance_hours)}>{hours(r.variance_hours) ?? '—'}</span>,
  },
  { id: 'allocated', label: 'Task value', numeric: true, value: (r) => (r.allocated_value == null ? null : Number(r.allocated_value)) },
]

const ENTRY_COLUMNS: DataColumn<TimeEntry>[] = [
  { id: 'date', label: 'Date', size: 120, value: (e) => e.work_date, cell: (e) => format(new Date(e.work_date), 'MMM d, yyyy') },
  { id: 'user', label: 'User', value: (e) => e.user.display_name },
  { id: 'project', label: 'Project', value: (e) => e.project_key, defaultHidden: true },
  { id: 'job', label: 'Task', size: 120, value: (e) => e.issue?.key, cell: (e) => (e.issue ? <IssueKey value={e.issue.key} /> : '—') },
  { id: 'job_summary', label: 'Task summary', size: 240, value: (e) => e.issue?.summary, defaultHidden: true },
  { id: 'description', label: 'Description', size: 260, value: (e) => e.description },
  { id: 'billable', label: 'Billable', size: 100, value: (e) => e.is_billable },
  { id: 'tags', label: 'Tags', value: (e) => e.tags.map((t) => t.name).join(', '), defaultHidden: true },
  { id: 'created_via', label: 'Created via', value: (e) => e.created_via, defaultHidden: true },
  { id: 'locked', label: 'Locked', value: (e) => e.locked, defaultHidden: true },
  { id: 'hours', label: 'Hours', numeric: true, value: (e) => Number((e.duration_seconds / 3600).toFixed(2)) },
]

function BudgetVsActualMode({ projectKey }: { projectKey: string }) {
  const { data, isLoading } = useBudgetVsActual(projectKey || undefined)

  if (isLoading || !data) return <Skeleton height={120} />

  if ('projects' in data) {
    return (
      <DataTable
        tableId="report-budget-projects"
        columns={PROJECT_COLUMNS}
        data={data.projects}
        getRowId={(r) => r.project_key}
        emptyMessage="No projects yet."
        exportName="budget-vs-actual"
        countLabel={(n) => `${n} project${n === 1 ? '' : 's'}`}
      />
    )
  }

  const { project, issues } = data
  return (
    <>
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{project.actual_hours.toFixed(1)}h</div>
          <div className={styles.statLabel}>of {project.budgeted_hours ?? '—'}h budgeted</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue} style={{ color: pctColor(project.pct_complete) }}>
            {project.pct_complete != null ? `${project.pct_complete}%` : '—'}
          </div>
          <div className={styles.statLabel}>Of budget used</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{money(project.job_value_currency, project.effective_cost)}</div>
          <div className={styles.statLabel}>Effective cost</div>
        </div>
      </div>
      <DataTable
        tableId="report-budget-jobs"
        columns={JOB_COLUMNS}
        data={issues}
        getRowId={(r) => r.issue_key}
        emptyMessage="No tasks with a budget or logged time yet."
        exportName={`budget-vs-actual-${project.project_key}`}
        countLabel={(n) => `${n} task${n === 1 ? '' : 's'}`}
      />
    </>
  )
}

export function TimeReportsPage() {
  const { data: projects } = useProjects()
  const { data: users } = useUsers()

  const [mode, setMode] = useState<'time' | 'budget'>('time')
  const [projectKey, setProjectKey] = useState('')
  const [userId, setUserId] = useState('')
  const [billable, setBillable] = useState<'all' | 'billable' | 'non_billable'>('all')
  const [dateFrom, setDateFrom] = useState(format(startOfMonth(new Date()), 'yyyy-MM-dd'))
  const [dateTo, setDateTo] = useState(format(new Date(), 'yyyy-MM-dd'))

  const params: TimeEntryQueryParams = {
    ...(projectKey ? { project: projectKey } : {}),
    ...(userId ? { user: Number(userId) } : {}),
    ...(billable !== 'all' ? { billable: billable === 'billable' } : {}),
    date_from: dateFrom,
    date_to: dateTo,
    page_size: 1000,
  }

  const { data: entries, isLoading } = useTimeEntries(params)

  const totalHours = (entries ?? []).reduce((sum, e) => sum + e.duration_seconds, 0) / 3600
  const billableHours = (entries ?? [])
    .filter((e) => e.is_billable)
    .reduce((sum, e) => sum + e.duration_seconds, 0) / 3600

  const byProject = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of entries ?? []) {
      const key = e.project_key ?? 'No project'
      map.set(key, (map.get(key) ?? 0) + e.duration_seconds / 3600)
    }
    return [...map.entries()].map(([name, hours]) => ({ name, hours: Number(hours.toFixed(2)) }))
  }, [entries])

  return (
    <div className={styles.page}>
      <Link to="/timesheets" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, marginBottom: 12 }}>
        <ArrowLeft size={13} /> My timesheet
      </Link>
      <div className={styles.header}>
        <h1 className={styles.title}>Time reports</h1>
      </div>

      <div style={{ display: 'inline-flex', border: '1px solid var(--tf-border)', borderRadius: 6, overflow: 'hidden', marginBottom: 16 }}>
        {(['time', 'budget'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              fontSize: 13,
              padding: '6px 14px',
              border: 'none',
              cursor: 'pointer',
              background: mode === m ? 'var(--tf-primary-subtle)' : 'var(--tf-surface)',
              color: mode === m ? 'var(--tf-primary)' : 'var(--tf-text)',
              fontWeight: mode === m ? 600 : 400,
            }}
          >
            {m === 'time' ? 'Time entries' : 'Budget vs actual'}
          </button>
        ))}
      </div>

      <div className={styles.filters}>
        <select className={styles.select} value={projectKey} onChange={(e) => setProjectKey(e.target.value)}>
          <option value="">All projects</option>
          {(projects ?? []).map((p) => (
            <option key={p.key} value={p.key}>
              {p.name}
            </option>
          ))}
        </select>
        {mode === 'time' && (
          <>
            <select className={styles.select} value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">Everyone</option>
              {(users ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name}
                </option>
              ))}
            </select>
            <select className={styles.select} value={billable} onChange={(e) => setBillable(e.target.value as typeof billable)}>
              <option value="all">All time</option>
              <option value="billable">Billable only</option>
              <option value="non_billable">Non-billable only</option>
            </select>
            <input
              type="date"
              className={styles.select}
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
            <span className={styles.dateSep}>to</span>
            <input type="date" className={styles.select} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </>
        )}
      </div>

      {mode === 'budget' ? (
        <BudgetVsActualMode projectKey={projectKey} />
      ) : (
        <>
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{totalHours.toFixed(1)}h</div>
          <div className={styles.statLabel}>Total hours</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{billableHours.toFixed(1)}h</div>
          <div className={styles.statLabel}>Billable hours</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{(entries ?? []).length}</div>
          <div className={styles.statLabel}>Entries</div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Hours by project</div>
        <div style={{ height: 180 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byProject}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--tf-border)" />
              <XAxis dataKey="name" fontSize={12} stroke="var(--tf-text-subtle)" />
              <YAxis allowDecimals={false} fontSize={12} stroke="var(--tf-text-subtle)" />
              <Tooltip />
              <Bar dataKey="hours" fill="var(--tf-primary)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <DataTable
        tableId="report-time-entries"
        columns={ENTRY_COLUMNS}
        data={entries ?? []}
        getRowId={(e) => String(e.id)}
        isLoading={isLoading}
        emptyMessage="No time entries for this filter."
        exportName={`time-report-${dateFrom}-to-${dateTo}`}
        defaultSort={[{ id: 'date', desc: true }]}
        countLabel={(n) => `${n} entr${n === 1 ? 'y' : 'ies'}`}
      />
        </>
      )}
    </div>
  )
}
