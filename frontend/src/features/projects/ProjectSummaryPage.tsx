import { format, subDays } from 'date-fns'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import styles from './ProjectSummaryPage.module.css'
import { useProjectContext } from './useProjectContext'
import { useTimeEntries } from '@/api/timesheets'
import { Avatar } from '@/design-system'

const PERIOD_DAYS = 30

export function ProjectSummaryPage() {
  const { project } = useProjectContext()
  const [billableFilter, setBillableFilter] = useState<'all' | 'billable' | 'non_billable'>('all')

  const dateFrom = format(subDays(new Date(), PERIOD_DAYS), 'yyyy-MM-dd')
  const { data: entries } = useTimeEntries({
    project: project.key,
    date_from: dateFrom,
    page_size: 500,
    ...(billableFilter !== 'all' ? { billable: billableFilter === 'billable' } : {}),
  })

  const totalHours = (entries ?? []).reduce((sum, e) => sum + e.duration_seconds, 0) / 3600

  const hoursByMember = project.memberships.map((m) => ({
    name: m.user.display_name.split(' ')[0],
    hours: Number(
      (
        (entries ?? [])
          .filter((e) => e.user.id === m.user.id)
          .reduce((sum, e) => sum + e.duration_seconds, 0) / 3600
      ).toFixed(2),
    ),
  }))

  return (
    <div className={styles.page}>
      <div className={styles.breadcrumb}>Projects / {project.key}</div>
      <h1 className={styles.title}>{project.name}</h1>

      <div className={styles.grid}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{project.memberships.length}</div>
          <div className={styles.statLabel}>Team members</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{project.labels.length}</div>
          <div className={styles.statLabel}>Labels</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{project.versions.length}</div>
          <div className={styles.statLabel}>Versions</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{project.components.length}</div>
          <div className={styles.statLabel}>Components</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{totalHours.toFixed(1)}h</div>
          <div className={styles.statLabel}>Time logged (30d)</div>
        </div>
      </div>

      {project.description && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Description</div>
          <div>{project.description}</div>
        </div>
      )}

      <div className={styles.section}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div className={styles.sectionTitle} style={{ marginBottom: 0 }}>
            Time logged by member (last {PERIOD_DAYS} days)
          </div>
          <select
            value={billableFilter}
            onChange={(e) => setBillableFilter(e.target.value as typeof billableFilter)}
            style={{
              fontSize: 12,
              padding: '4px 8px',
              borderRadius: 'var(--tf-radius-sm)',
              border: '1px solid var(--tf-border)',
              background: 'var(--tf-surface)',
              color: 'var(--tf-text)',
            }}
          >
            <option value="all">All time</option>
            <option value="billable">Billable only</option>
            <option value="non_billable">Non-billable only</option>
          </select>
        </div>
        <div style={{ height: 180 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hoursByMember}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--tf-border)" />
              <XAxis dataKey="name" fontSize={12} stroke="var(--tf-text-subtle)" />
              <YAxis allowDecimals={false} fontSize={12} stroke="var(--tf-text-subtle)" />
              <Tooltip />
              <Bar dataKey="hours" fill="var(--tf-blue)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>People</div>
        {project.memberships.map((m) => (
          <div key={m.id} className={styles.memberRow}>
            <Avatar name={m.user.display_name} src={m.user.avatar} size={28} />
            <span className={styles.memberName}>{m.user.display_name}</span>
            <span className={styles.memberRole}>{m.role}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
