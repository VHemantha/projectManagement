import { addDays, format, startOfWeek, subWeeks } from 'date-fns'
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import styles from './UserWorkloadPage.module.css'
import { useIssues } from '@/api/issues'
import { useTimeEntries } from '@/api/timesheets'
import { useUsers } from '@/api/users'
import { Avatar } from '@/design-system'
import { IssueTable } from '@/features/tables/IssueTable'

export function UserWorkloadPage() {
  const { userId } = useParams<{ userId: string }>()
  const { data: users } = useUsers()
  const user = users?.find((u) => u.id === Number(userId))
  const [groupBy, setGroupBy] = useState<'none' | 'status' | 'assignee' | 'project'>('project')

  const { data: issuesPage, isLoading } = useIssues(
    { assignee: Number(userId), page_size: 300, ordering: 'rank' },
    !!userId,
  )
  const issues = issuesPage?.results ?? []

  const stats = useMemo(() => {
    const open = issues.filter((i) => i.status.category !== 'done').length
    const done = issues.filter((i) => i.status.category === 'done').length
    const overdue = issues.filter(
      (i) => i.due_date && i.status.category !== 'done' && new Date(i.due_date) < new Date(),
    ).length
    return { open, done, overdue }
  }, [issues])

  const thisWeekStart = startOfWeek(new Date(), { weekStartsOn: 1 })
  const lastWeekStart = subWeeks(thisWeekStart, 1)

  const { data: thisWeekEntries } = useTimeEntries(
    { user: Number(userId), date_from: format(thisWeekStart, 'yyyy-MM-dd'), date_to: format(addDays(thisWeekStart, 6), 'yyyy-MM-dd'), page_size: 500 },
    !!userId,
  )
  const { data: lastWeekEntries } = useTimeEntries(
    { user: Number(userId), date_from: format(lastWeekStart, 'yyyy-MM-dd'), date_to: format(addDays(lastWeekStart, 6), 'yyyy-MM-dd'), page_size: 500 },
    !!userId,
  )

  const hoursOf = (entries: typeof thisWeekEntries) =>
    (entries ?? []).reduce((sum, e) => sum + e.duration_seconds, 0) / 3600
  const thisWeekHours = hoursOf(thisWeekEntries)
  const lastWeekHours = hoursOf(lastWeekEntries)
  const billableHours = (thisWeekEntries ?? [])
    .filter((e) => e.is_billable)
    .reduce((sum, e) => sum + e.duration_seconds, 0) / 3600
  const billablePct = thisWeekHours > 0 ? Math.round((billableHours / thisWeekHours) * 100) : 0

  if (!user) return null

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Avatar name={user.display_name} src={user.avatar} size={48} />
        <div>
          <div className={styles.name}>{user.display_name}</div>
          <div className={styles.role}>{user.job_title || user.email}</div>
        </div>
      </div>

      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{stats.open}</div>
          <div className={styles.statLabel}>Open</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{stats.done}</div>
          <div className={styles.statLabel}>Done</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{stats.overdue}</div>
          <div className={styles.statLabel}>Overdue</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{thisWeekHours.toFixed(1)}h</div>
          <div className={styles.statLabel}>
            Hours this week {lastWeekHours > 0 && <span>({lastWeekHours.toFixed(1)}h last week)</span>}
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{billablePct}%</div>
          <div className={styles.statLabel}>Billable this week</div>
        </div>
      </div>

      <IssueTable
        issues={issues}
        isLoading={isLoading}
        groupBy={groupBy}
        onGroupByChange={setGroupBy}
        availableGroupBy={['none', 'project', 'status']}
        showProjectColumn
        emptyMessage="No issues assigned."
      />
    </div>
  )
}
