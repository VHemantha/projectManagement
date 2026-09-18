import { formatDistanceToNow } from 'date-fns'
import { Eye, EyeOff } from 'lucide-react'
import { Link } from 'react-router-dom'

import styles from './IssueView.module.css'
import { useProjectBoard } from '@/api/projects'
import { useToggleWatch, useUpdateIssue } from '@/api/issues'
import type { IssueDetail, Priority } from '@/api/types'
import { useUsers } from '@/api/users'
import { Avatar, PriorityIcon } from '@/design-system'

const PRIORITIES: Priority[] = ['highest', 'high', 'medium', 'low', 'lowest']

export function IssueDetailsPanel({ issue }: { issue: IssueDetail }) {
  const updateIssue = useUpdateIssue(issue.key)
  const toggleWatch = useToggleWatch(issue.key)
  const { data: users } = useUsers()
  const { data: board } = useProjectBoard(issue.project)

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

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Assignee</span>
        <div className={styles.assigneeRow}>
          <Avatar name={issue.assignee?.display_name ?? 'Unassigned'} src={issue.assignee?.avatar} size={24} />
          <select
            className={styles.panelSelect}
            value={issue.assignee?.id ?? ''}
            onChange={(e) =>
              updateIssue.mutate({ assignee_id: e.target.value ? Number(e.target.value) : null })
            }
          >
            <option value="">Unassigned</option>
            {users?.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Reporter</span>
        <Link to={`/people/${issue.reporter.id}`} className={styles.assigneeRow} style={{ textDecoration: 'none', color: 'inherit' }}>
          <Avatar name={issue.reporter.display_name} src={issue.reporter.avatar} size={24} />
          <span style={{ fontSize: 13 }}>{issue.reporter.display_name}</span>
        </Link>
      </div>

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
