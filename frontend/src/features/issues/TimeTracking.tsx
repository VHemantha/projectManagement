import { Link } from 'react-router-dom'

import styles from './TimeTracking.module.css'
import { useUpdateIssue } from '@/api/issues'
import type { IssueDetail } from '@/api/types'

const fmt = (hours: number) => `${Number(hours.toFixed(2))}h`

/** Actual time (logged in timesheets) against the job's budget: progress, what's left or over,
 * and who logged it. The budget is editable here. */
export function TimeTracking({ issue }: { issue: IssueDetail }) {
  const updateIssue = useUpdateIssue(issue.key)
  const budget = issue.budgeted_hours
  const actual = issue.actual_hours
  const pct = budget ? Math.round((actual / budget) * 100) : null
  const over = budget != null && actual > budget

  return (
    <div className={styles.box} data-testid="time-tracking">
      <div className={styles.figures}>
        <div>
          <div className={styles.value}>{fmt(actual)}</div>
          <div className={styles.caption}>Actual (timesheets)</div>
        </div>
        <label className={styles.budget}>
          <input
            className={styles.budgetInput}
            type="number"
            min={0}
            step="0.25"
            aria-label="Budgeted hours"
            value={budget ?? ''}
            placeholder="—"
            onChange={(e) => updateIssue.mutate({ budgeted_hours: e.target.value ? Number(e.target.value) : null })}
          />
          <span className={styles.caption}>Budgeted (h)</span>
        </label>
      </div>

      {budget != null && budget > 0 && (
        <>
          <div className={styles.bar} role="progressbar" aria-valuenow={pct ?? 0} aria-valuemin={0} aria-valuemax={100}>
            <span
              className={styles.fill}
              data-over={over}
              style={{ width: `${Math.min(pct ?? 0, 100)}%` }}
            />
          </div>
          <div className={styles.status} data-over={over}>
            {over ? `${fmt(actual - budget)} over budget` : `${fmt(budget - actual)} remaining`} · {pct}% used
          </div>
        </>
      )}
      {budget == null && <div className={styles.hint}>Set a budget to compare it with the time logged.</div>}

      {issue.time_by_user.length > 0 && (
        <ul className={styles.people}>
          {issue.time_by_user.map((row) => (
            <li key={row.user_id}>
              <span>{row.display_name}</span>
              <span className={styles.hours}>{fmt(row.hours)}</span>
            </li>
          ))}
        </ul>
      )}
      <Link to="/timesheets/reports" className={styles.link}>
        Time reports
      </Link>
    </div>
  )
}
