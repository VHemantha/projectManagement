import { format, parseISO } from 'date-fns'
import { Check, X } from 'lucide-react'
import { useState } from 'react'

import { DailyGoalsWidget, PlanMeta } from './DailyGoalsWidget'
import styles from './MorningPlansPage.module.css'
import { type DailyGoal, type TeamPlanRow, useCheckGoal, useTeamPlans } from '@/api/dailyGoals'
import { Avatar, IssueKey, Skeleton } from '@/design-system'
import { useUiStore } from '@/store/uiStore'

const STATUS_LABEL: Record<DailyGoal['status'], string> = {
  planned: 'Planned',
  in_progress: 'In progress',
  achieved: 'Done',
  not_achieved: 'Not done',
  carried_over: 'Carried over',
}
const STATUS_TONE: Record<DailyGoal['status'], string> = {
  planned: '',
  in_progress: '',
  achieved: 'success',
  not_achieved: 'danger',
  carried_over: 'warning',
}

const hrs = (n: number) => `${Number(n.toFixed(2))} hr${n === 1 ? '' : 's'}`

/** One plan item as the team lead sees it, with their check: confirmed done, or not done. */
function PlanItem({ goal }: { goal: DailyGoal }) {
  const check = useCheckGoal()
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const set = (result: DailyGoal['lead_check']) => check.mutate({ id: goal.id, result: goal.lead_check === result ? '' : result })
  return (
    <li className={styles.item}>
      <div className={styles.itemMain}>
        <span className={styles.itemText}>
          {goal.text}
          {goal.linked_issue && (
            <button type="button" className={styles.keyButton} onClick={() => openIssueModal(goal.linked_issue!.key)}>
              <IssueKey value={goal.linked_issue.key} />
            </button>
          )}
        </span>
        <PlanMeta goal={goal} />
        {goal.note && goal.status !== 'achieved' && <small className={styles.note}>Why not: {goal.note}</small>}
      </div>
      <span className={styles.chip} data-tone={STATUS_TONE[goal.status]}>
        {STATUS_LABEL[goal.status]}
      </span>
      <span className={styles.checks} role="group" aria-label={`Check: ${goal.text}`}>
        <button
          type="button"
          className={styles.checkButton}
          data-on={goal.lead_check === 'confirmed'}
          aria-pressed={goal.lead_check === 'confirmed'}
          title="Confirm it was done"
          onClick={() => set('confirmed')}
          disabled={check.isPending}
        >
          <Check size={13} aria-hidden="true" /> Done
        </button>
        <button
          type="button"
          className={styles.checkButton}
          data-on={goal.lead_check === 'not_done'}
          data-tone="danger"
          aria-pressed={goal.lead_check === 'not_done'}
          title="Mark it not done"
          onClick={() => set('not_done')}
          disabled={check.isPending}
        >
          <X size={13} aria-hidden="true" /> Not done
        </button>
      </span>
    </li>
  )
}

function PersonPlan({ row }: { row: TeamPlanRow }) {
  const short = row.planned_hours > 0 && row.logged_hours > 0 && row.logged_hours < row.planned_hours
  return (
    <section className={styles.person} aria-label={row.person.display_name}>
      <header className={styles.personHeader}>
        <Avatar name={row.person.display_name} src={row.person.avatar} size={26} userId={row.person.id} interactive />
        <strong>{row.person.display_name}</strong>
        {row.goals.length === 0 ? (
          <span className={styles.muted}>No plan set</span>
        ) : (
          <span className={styles.figures}>
            <span>{hrs(row.planned_hours)} planned</span>
            <span data-tone={short ? 'warning' : ''}>{hrs(row.logged_hours)} logged</span>
            <span data-tone="success">{row.achieved} done</span>
            <span data-tone={row.not_achieved ? 'danger' : ''}>{row.not_achieved} not done</span>
            {row.unchecked > 0 && <span>{row.unchecked} to check</span>}
          </span>
        )}
      </header>
      {row.goals.length > 0 && (
        <ul className={styles.items}>
          {row.goals.map((g) => (
            <PlanItem key={g.id} goal={g} />
          ))}
        </ul>
      )}
    </section>
  )
}

/** Morning plans (AFIT, 1 Nov 2026): your own plan for the day (each item with its hours and
 * completion date) and, for a team lead, everyone they lead: what was planned, what is done and
 * what is not, checked by the lead. Plans kept count toward each person's rating. */
export function MorningPlansPage() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const [date, setDate] = useState(today)
  const { data, isLoading, isError } = useTeamPlans(date)
  const people = data?.people ?? []
  const planned = people.filter((p) => p.goals.length > 0)

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <h1 className={styles.title}>Morning plans</h1>
      </header>
      <div className={styles.layout}>
        <div className={styles.mine}>
          <DailyGoalsWidget />
        </div>
        {(isLoading || isError || people.length > 0) && (
          <section className={styles.team} aria-label="Team plans">
            <div className={styles.teamHeader}>
              <h2 className={styles.subtitle}>Your team&apos;s plans</h2>
              <label className={styles.dateLabel}>
                Day
                <input type="date" value={date} max={today} onChange={(e) => setDate(e.target.value || today)} />
              </label>
            </div>
            {isLoading ? (
              <Skeleton height={120} />
            ) : isError ? (
              <p className={styles.muted}>The team&apos;s plans could not be loaded.</p>
            ) : (
              <>
                <p className={styles.muted}>
                  {format(parseISO(date), 'EEEE d MMMM')}: {planned.length} of {people.length} people have a plan. Check each
                  item; your &quot;Not done&quot; overrules their own tick. Plans kept count toward each person&apos;s rating
                  (Morning plans kept).
                </p>
                {people.map((row) => (
                  <PersonPlan key={row.person.id} row={row} />
                ))}
              </>
            )}
          </section>
        )}
      </div>
    </div>
  )
}
