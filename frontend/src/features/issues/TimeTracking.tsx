import { format } from 'date-fns'
import { Clock } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './TimeTracking.module.css'
import { TimesheetBreakdownLink } from './TimesheetBreakdown'
import { useUpdateIssue } from '@/api/issues'
import type { IssueDetail } from '@/api/types'
import { LogTimeModal } from '@/features/timesheets/LogTimeModal'

const fmt = (hours: number) => `${Number(hours.toFixed(2))}h`

/** The task's time budget (AFIT, 12 Nov 2026 design): hours logged in timesheets against the
 * accountant's estimate, the budget a team lead sets (it feeds the KPI), a bar of time used, who
 * logged it, and Log time. */
export function TimeTracking({ issue }: { issue: IssueDetail }) {
  const updateIssue = useUpdateIssue(issue.key)
  const [logging, setLogging] = useState(false)
  const budget = issue.budgeted_hours
  const estimate = issue.estimated_hours ?? null
  const actual = issue.actual_hours
  // The bar measures against the budget; without one, against the estimate.
  const target = budget || estimate || null
  const pct = target ? Math.round((actual / target) * 100) : null
  const over = target != null && actual > target

  return (
    <section className={styles.box} data-testid="time-tracking" aria-label="Time budget">
      <h3 className={styles.title}>
        <Clock size={18} aria-hidden="true" /> Time budget
      </h3>
      <div className={styles.figures}>
        <div className={styles.figure}>
          <div className={styles.value}>
            <TimesheetBreakdownLink issueId={issue.id} issueKey={issue.key} title={issue.summary} label="Actual time: open the timesheet breakup">
              {fmt(actual)}
            </TimesheetBreakdownLink>
          </div>
          <div className={styles.caption}>logged</div>
        </div>
        <div className={styles.figure}>
          <div className={styles.value}>{estimate != null ? fmt(estimate) : '—'}</div>
          <div className={styles.caption}>estimated</div>
        </div>
        <label className={styles.figure}>
          <input
            className={styles.budgetInput}
            type="number"
            min={0}
            step="0.25"
            aria-label="Budgeted hours"
            // Budgeted time feeds the assignee's KPI: only a team lead or above sets it.
            readOnly={issue.can_set_budget === false}
            title={issue.can_set_budget === false ? 'Only a team lead or above can set the budgeted time' : undefined}
            value={budget ?? ''}
            placeholder="—"
            onChange={(e) => updateIssue.mutate({ budgeted_hours: e.target.value ? Number(e.target.value) : null })}
          />
          <span className={styles.caption}>budgeted</span>
        </label>
      </div>

      <div className={styles.footer}>
        <div className={styles.barWrap}>
          <div
            className={styles.bar}
            role="progressbar"
            aria-label={budget ? 'Time used of the budget' : 'Time used of the estimate'}
            aria-valuenow={pct ?? 0}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <span className={styles.fill} data-over={over} style={{ width: `${Math.min(pct ?? 0, 100)}%` }} />
          </div>
          {target != null && target > 0 ? (
            <div className={styles.status} data-over={over}>
              {over ? `${fmt(actual - target)} over ${budget ? 'budget' : 'the estimate'}` : `${fmt(target - actual)} remaining`} · {pct}%
            </div>
          ) : (
            <div className={styles.hint}>Set an estimate or budget to compare it with the time logged.</div>
          )}
        </div>
        <button type="button" className={styles.logButton} onClick={() => setLogging(true)}>
          <Clock size={14} aria-hidden="true" /> Log time
        </button>
      </div>

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
      {logging && (
        <LogTimeModal
          open
          onOpenChange={setLogging}
          defaultDate={format(new Date(), 'yyyy-MM-dd')}
          defaultIssueId={issue.id}
          projectKey={issue.project}
        />
      )}
    </section>
  )
}
