import { format } from 'date-fns'
import { useState } from 'react'
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

import styles from './SprintReportPage.module.css'
import { useSprintBurndown, useSprints, useVelocity } from '@/api/sprints'
import { useProjectContext } from '@/features/projects/useProjectContext'

export function SprintReportPage() {
  const { project } = useProjectContext()
  const { data: sprints } = useSprints(project.key)
  const { data: velocity } = useVelocity(project.key)

  const reportable = (sprints ?? []).filter((s) => s.state !== 'future')
  const [sprintId, setSprintId] = useState<number | undefined>(undefined)
  const activeSprintId = sprintId ?? reportable.find((s) => s.state === 'active')?.id ?? reportable[0]?.id

  const { data: burndown } = useSprintBurndown(activeSprintId)

  const burndownData = (burndown?.dates ?? []).map((d, i) => ({
    date: format(new Date(d), 'MMM d'),
    ideal: burndown!.ideal[i],
    remaining: burndown!.remaining[i],
  }))

  if (project.project_type !== 'scrum') {
    return <div className={styles.page}>Reports are available for Scrum projects.</div>
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Reports</h1>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Sprint burndown</div>
        {reportable.length === 0 ? (
          <div className={styles.empty}>No sprints with dates yet.</div>
        ) : (
          <>
            <select
              className={styles.select}
              value={activeSprintId}
              onChange={(e) => setSprintId(Number(e.target.value))}
            >
              {reportable.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} {s.state === 'active' ? '(active)' : ''}
                </option>
              ))}
            </select>
            {!burndown ? (
              <div className={styles.empty}>No burndown data for this sprint.</div>
            ) : (
              <>
                <div className={styles.chartBox}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={burndownData} margin={{ left: -12 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--tf-border)" vertical={false} />
                      <XAxis dataKey="date" fontSize={11} stroke="var(--tf-text-subtle)" tickLine={false} />
                      <YAxis fontSize={11} stroke="var(--tf-text-subtle)" tickLine={false} allowDecimals={false} />
                      <Tooltip />
                      <Line
                        type="monotone"
                        dataKey="ideal"
                        name="Ideal"
                        stroke="var(--tf-text-subtle)"
                        strokeWidth={2}
                        strokeDasharray="4 4"
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="remaining"
                        name="Remaining"
                        stroke="var(--tf-blue)"
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        connectNulls={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className={styles.legend}>
                  <span className={styles.legendItem}>
                    <span className={styles.swatch} style={{ background: 'var(--tf-blue)' }} /> Remaining points
                  </span>
                  <span className={styles.legendItem}>
                    <span className={styles.swatch} style={{ background: 'var(--tf-text-subtle)' }} /> Ideal burn
                  </span>
                </div>
              </>
            )}
          </>
        )}
      </div>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Velocity</div>
        {!velocity || velocity.length === 0 ? (
          <div className={styles.empty}>No closed sprints yet.</div>
        ) : (
          <>
            <div className={styles.chartBox}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={velocity} margin={{ left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--tf-border)" vertical={false} />
                  <XAxis dataKey="sprint" fontSize={11} stroke="var(--tf-text-subtle)" tickLine={false} />
                  <YAxis fontSize={11} stroke="var(--tf-text-subtle)" tickLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="committed" name="Committed" fill="var(--tf-status-todo-bg)" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="completed" name="Completed" fill="var(--tf-success)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
