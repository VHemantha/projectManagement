import { formatDistanceToNow } from 'date-fns'
import { Eye, EyeOff } from 'lucide-react'
import { Link } from 'react-router-dom'

import styles from './IssueView.module.css'
import { RolePicker } from './RolePicker'
import { useProjectBoard } from '@/api/projects'
import { useToggleWatch, useUpdateIssue } from '@/api/issues'
import type { IssueDetail, Priority } from '@/api/types'
import { useTimeEntries } from '@/api/timesheets'
import { useUsers } from '@/api/users'
import { Avatar, PriorityIcon } from '@/design-system'

const PRIORITIES: Priority[] = ['highest', 'high', 'medium', 'low', 'lowest']

export function IssueDetailsPanel({ issue }: { issue: IssueDetail }) {
  const updateIssue = useUpdateIssue(issue.key)
  const toggleWatch = useToggleWatch(issue.key)
  const { data: users } = useUsers()
  const { data: board } = useProjectBoard(issue.project)
  const { data: issueEntries } = useTimeEntries({ issue: issue.id, page_size: 500 }, issue.budgeted_hours != null)
  const actualHours = (issueEntries ?? []).reduce((sum, e) => sum + e.duration_seconds, 0) / 3600

  return (
    <div className={styles.panel}>
      <button
        type="button"
        className={styles.watchBtn}
        data-active={issue.is_watching}
        onClick={() => toggleWatch.mutate(!issue.is_watching)}
      >
        {issue.is_watching ? <Eye size={14} /> : <EyeOff size={14} />}
        {issue.is_watching ? 'Watching' : 'Watch'} ({issue.watcher_count})
      </button>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Status</span>
        <select
          className={styles.panelSelect}
          value={issue.status.id}
          onChange={(e) => updateIssue.mutate({ status_id: Number(e.target.value) })}
        >
          {board?.statuses.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      <RolePicker
        label="Assignee"
        value={issue.assignee}
        users={users}
        onChange={(id) => updateIssue.mutate({ assignee_id: id })}
      />

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Reporter</span>
        <Link to={`/people/${issue.reporter.id}`} className={styles.assigneeRow} style={{ textDecoration: 'none', color: 'inherit' }}>
          <Avatar name={issue.reporter.display_name} src={issue.reporter.avatar} size={24} />
          <span style={{ fontSize: 13 }}>{issue.reporter.display_name}</span>
        </Link>
      </div>

      <div className={styles.divider} />

      <RolePicker
        label="Preparer"
        value={issue.preparer}
        users={users}
        onChange={(id) => updateIssue.mutate({ preparer_id: id })}
        emptyLabel="Unset"
      />
      <RolePicker
        label="Reviewer"
        value={issue.reviewer}
        users={users}
        onChange={(id) => updateIssue.mutate({ reviewer_id: id })}
        emptyLabel="Unset"
      />
      <RolePicker
        label="Current responsible"
        value={issue.current_responsible}
        users={users}
        onChange={(id) => updateIssue.mutate({ current_responsible_id: id })}
        emptyLabel="Unset"
      />

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Priority</span>
        <select
          className={styles.panelSelect}
          value={issue.priority}
          onChange={(e) => updateIssue.mutate({ priority: e.target.value })}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {p[0].toUpperCase() + p.slice(1)}
            </option>
          ))}
        </select>
        <div style={{ marginTop: 2 }}>
          <PriorityIcon priority={issue.priority} />
        </div>
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Story points</span>
        <input
          className={styles.panelSelect}
          type="number"
          min={0}
          value={issue.story_points ?? ''}
          onChange={(e) =>
            updateIssue.mutate({ story_points: e.target.value ? Number(e.target.value) : null })
          }
        />
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Budgeted hours</span>
        <input
          className={styles.panelSelect}
          type="number"
          min={0}
          value={issue.budgeted_hours ?? ''}
          onChange={(e) =>
            updateIssue.mutate({ budgeted_hours: e.target.value ? Number(e.target.value) : null })
          }
        />
        {issue.budgeted_hours != null && (
          <div style={{ fontSize: 12, color: 'var(--tf-text-subtle)', marginTop: 4 }}>
            {actualHours.toFixed(1)} of {issue.budgeted_hours} hrs budgeted
          </div>
        )}
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Due date</span>
        <input
          className={styles.panelSelect}
          type="date"
          value={issue.due_date ?? ''}
          onChange={(e) => updateIssue.mutate({ due_date: e.target.value || null })}
        />
      </div>

      {issue.labels.length > 0 && (
        <div className={styles.panelRow}>
          <span className={styles.panelLabel}>Labels</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {issue.labels.map((l) => (
              <span
                key={l.id}
                style={{
                  fontSize: 12,
                  padding: '2px 8px',
                  borderRadius: 3,
                  background: l.color,
                  color: '#172B4D',
                }}
              >
                {l.name}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className={styles.divider} />

      <div className={styles.metaText}>
        Created {formatDistanceToNow(new Date(issue.created_at), { addSuffix: true })}
      </div>
      <div className={styles.metaText}>
        Updated {formatDistanceToNow(new Date(issue.updated_at), { addSuffix: true })}
      </div>
    </div>
  )
}
