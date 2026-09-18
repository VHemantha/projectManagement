import { format, startOfMonth } from 'date-fns'
import { ArrowLeft, Download } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router-dom'

import styles from './TimeReportsPage.module.css'
import { useProjects } from '@/api/projects'
import { downloadTimeReportCsv, useTimeEntries, type TimeEntryQueryParams } from '@/api/timesheets'
import { useUsers } from '@/api/users'
import { Button, IssueKey, Skeleton } from '@/design-system'

export function TimeReportsPage() {
  const { data: projects } = useProjects()
  const { data: users } = useUsers()

  const [projectKey, setProjectKey] = useState('')
  const [userId, setUserId] = useState('')
  const [billable, setBillable] = useState<'all' | 'billable' | 'non_billable'>('all')
  const [dateFrom, setDateFrom] = useState(format(startOfMonth(new Date()), 'yyyy-MM-dd'))
  const [dateTo, setDateTo] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [exporting, setExporting] = useState(false)

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

  const handleExport = async () => {
    setExporting(true)
    try {
      await downloadTimeReportCsv(params)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className={styles.page}>
      <Link to="/timesheets" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 13, marginBottom: 12 }}>
        <ArrowLeft size={13} /> My timesheet
      </Link>
      <div className={styles.header}>
        <h1 className={styles.title}>Time reports</h1>
        <Button variant="secondary" size="sm" disabled={exporting} onClick={handleExport} style={{ marginLeft: 'auto' }}>
          <Download size={14} /> Export CSV
        </Button>
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
      </div>

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
              <Bar dataKey="hours" fill="var(--tf-blue)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Date</th>
            <th>User</th>
            <th>Issue</th>
            <th>Description</th>
            <th>Billable</th>
            <th>Hours</th>
          </tr>
        </thead>
        <tbody>
          {isLoading &&
            [0, 1, 2, 3].map((row) => (
              <tr key={row}>
                <td colSpan={6} style={{ padding: '10px 12px' }}>
                  <Skeleton height={12} width={row % 2 === 0 ? '85%' : '65%'} />
                </td>
              </tr>
            ))}
          {!isLoading && (entries ?? []).length === 0 && (
            <tr>
              <td colSpan={6} className={styles.empty}>
                No time entries for this filter.
              </td>
            </tr>
          )}
          {(entries ?? []).map((e) => (
            <tr key={e.id}>
              <td>{format(new Date(e.work_date), 'MMM d, yyyy')}</td>
              <td>{e.user.display_name}</td>
              <td>{e.issue ? <IssueKey value={e.issue.key} /> : '—'}</td>
              <td className={styles.description}>{e.description || '—'}</td>
              <td>{e.is_billable ? 'Yes' : 'No'}</td>
              <td className={styles.hoursCell}>{(e.duration_seconds / 3600).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
