import { formatDistanceToNow } from 'date-fns'
import { useMemo } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

import styles from './DashboardHomePage.module.css'
import { useIssues, useRecentActivity } from '@/api/issues'
import { IssueKey, IssueTypeIcon, StatusBadge } from '@/design-system'
import type { StatusCategory } from '@/design-system'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'

const CATEGORY_LABEL: Record<string, string> = { todo: 'To Do', in_progress: 'In Progress', done: 'Done' }
const CATEGORY_COLOR: Record<string, string> = {
  todo: 'var(--tf-status-todo-text)',
  in_progress: 'var(--tf-status-inprogress-text)',
  done: 'var(--tf-status-done-text)',
}

const FIELD_LABELS: Record<string, string> = {
  summary: 'summary',
  status: 'status',
  priority: 'priority',
  assignee: 'assignee',
  sprint: 'sprint',
}

export function DashboardHomePage() {
  const currentUser = useAuthStore((s) => s.user)
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const { data: myIssuesPage } = useIssues(
    { assignee: currentUser?.id, no_parent: true, page_size: 100, ordering: 'rank' },
    !!currentUser,
  )
  const { data: activity } = useRecentActivity()

  const myIssues = myIssuesPage?.results ?? []

  const pieData = useMemo(() => {
    const counts: Record<string, number> = { todo: 0, in_progress: 0, done: 0 }
    for (const i of myIssues) counts[i.status.category] = (counts[i.status.category] ?? 0) + 1
    return (['todo', 'in_progress', 'done'] as const)
      .map((cat) => ({ category: cat, label: CATEGORY_LABEL[cat], value: counts[cat] }))
      .filter((d) => d.value > 0)
  }, [myIssues])

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Welcome back{currentUser ? `, ${currentUser.display_name.split(' ')[0]}` : ''}</h1>

      <div className={styles.grid}>
        <div>
          <div className={styles.card}>
            <div className={styles.cardTitle}>Assigned to me ({myIssues.length})</div>
            {myIssues.length === 0 ? (
              <div className={styles.empty}>Nothing assigned to you right now.</div>
            ) : (
              myIssues.slice(0, 8).map((issue) => (
                <div key={issue.id} className={styles.issueRow} onClick={() => openIssueModal(issue.key)}>
                  <IssueTypeIcon typeName={issue.issue_type.name} size={13} />
                  <IssueKey value={issue.key} />
                  <span className={styles.summary}>{issue.summary}</span>
                  <StatusBadge label={issue.status.name} category={issue.status.category as StatusCategory} />
                </div>
              ))
            )}
          </div>

          <div className={styles.card}>
            <div className={styles.cardTitle}>Recent activity</div>
            {!activity || activity.length === 0 ? (
              <div className={styles.empty}>No recent activity yet.</div>
            ) : (
              activity.slice(0, 8).map((a) => (
                <div key={a.id} className={styles.activityRow} onClick={() => openIssueModal(a.issue_key)} style={{ cursor: 'pointer' }}>
                  <div>
                    <div className={styles.activityText}>
                      <strong>{a.user?.display_name ?? 'Someone'}</strong> changed{' '}
                      {FIELD_LABELS[a.field_changed] ?? a.field_changed} on{' '}
                      <strong>
                        <IssueKey value={a.issue_key} />
                      </strong>{' '}
                      {a.old_value && a.new_value ? (
                        <>
                          from <strong>{a.old_value}</strong> to <strong>{a.new_value}</strong>
                        </>
                      ) : (
                        <>to {a.new_value || 'none'}</>
                      )}
                    </div>
                    <div className={styles.activityTime}>
                      {formatDistanceToNow(new Date(a.timestamp), { addSuffix: true })}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>My issues by status</div>
          {pieData.length === 0 ? (
            <div className={styles.empty}>No data yet.</div>
          ) : (
            <>
              <div className={styles.pieBox}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="label" innerRadius={50} outerRadius={80} paddingAngle={2}>
                      {pieData.map((d) => (
                        <Cell key={d.category} fill={CATEGORY_COLOR[d.category]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className={styles.pieLegend}>
                {pieData.map((d) => (
                  <div key={d.category} className={styles.pieLegendItem}>
                    <span
                      style={{ width: 10, height: 10, borderRadius: 2, background: CATEGORY_COLOR[d.category] }}
                    />
                    {d.label} ({d.value})
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
