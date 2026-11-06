import { format, parseISO } from 'date-fns'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './PeopleSnapshot.module.css'
import { type DoingNow, type PeopleSnapshotRow, usePeopleSnapshot } from '@/api/reports'
import { Avatar, Skeleton } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

type Sort = 'name' | 'overdue' | 'open' | 'hours'

const SORTS: Record<Sort, { label: string; by: (a: PeopleSnapshotRow, b: PeopleSnapshotRow) => number }> = {
  name: { label: 'Name', by: (a, b) => a.person.display_name.localeCompare(b.person.display_name) },
  overdue: { label: 'Most overdue', by: (a, b) => b.overdue - a.overdue || b.open - a.open },
  open: { label: 'Most open jobs', by: (a, b) => b.open - a.open },
  hours: { label: 'Fewest hours this week', by: (a, b) => a.hours_week - b.hours_week },
}

export function DoingNowLine({ doing }: { doing: DoingNow | null }) {
  if (!doing) return <span className={styles.idle}>No timer running</span>
  return (
    <span className={styles.doing}>
      <span className={styles.live} aria-hidden="true" />
      Working on {doing.key && <strong>{doing.key}</strong>} {doing.sub_workspace ? `${doing.sub_workspace} · ` : ''}
      {doing.summary}
      {doing.since && <span className={styles.since}> since {format(parseISO(doing.since), 'HH:mm')}</span>}
    </span>
  )
}

function PersonCard({ row }: { row: PeopleSnapshotRow }) {
  const p = row.person
  return (
    <Link to={`/people/work/${p.id}`} className={styles.personCard} aria-label={`${p.display_name}: open their work`}>
      <div className={styles.personTop}>
        <Avatar name={p.display_name} src={p.avatar ?? undefined} size={32} userId={p.id} />
        <div className={styles.personName}>
          <strong>{p.display_name}</strong>
          {p.job_title && <small>{p.job_title}</small>}
        </div>
        {row.on_leave && <span className={styles.chip} data-tone="warning">On leave</span>}
        {row.rating && <span className={styles.chip} title={`Rating to ${format(parseISO(row.rating.period_end), 'd MMM')}`}>{row.rating.rating}</span>}
      </div>
      <DoingNowLine doing={row.doing_now} />
      <dl className={styles.figures}>
        <div><dt>Open</dt><dd>{row.open}</dd></div>
        <div><dt>In progress</dt><dd>{row.in_progress}</dd></div>
        <div data-tone={row.overdue ? 'danger' : ''}><dt>Overdue</dt><dd>{row.overdue}</dd></div>
        <div data-tone={row.completed_30_days ? 'success' : ''}><dt>Done, 30 days</dt><dd>{row.completed_30_days}</dd></div>
        <div><dt>Hours today</dt><dd>{row.hours_today}</dd></div>
        <div><dt>Hours this week</dt><dd>{row.hours_week}</dd></div>
      </dl>
    </Link>
  )
}

/** The CEO's snapshot of everyone's work (AFIT, 5 Nov 2026): what each person is doing now, their
 * open, in-progress, overdue and finished jobs and their hours; open a person for their dashboard. */
export function TeamSnapshotPage() {
  const isCeo = useAuthStore((s) => s.user?.role === 'ceo')
  const { data, isLoading, isError } = usePeopleSnapshot()
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>('overdue')

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (data?.people ?? [])
      .filter((r) => !q || r.person.display_name.toLowerCase().includes(q) || r.person.job_title.toLowerCase().includes(q))
      .sort(SORTS[sort].by)
  }, [data, query, sort])

  if (!isCeo) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Team snapshot</h1>
        <p className={styles.muted}>Only the CEO can see everyone&apos;s work snapshot.</p>
      </div>
    )
  }

  const people = data?.people ?? []
  const working = people.filter((r) => r.doing_now).length
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Team snapshot</h1>
        {data && (
          <span className={styles.muted}>
            {working} of {people.length} working on something now · as of {format(parseISO(data.as_of), 'HH:mm')}
          </span>
        )}
      </header>
      <div className={styles.toolbar}>
        <input aria-label="Find a person" placeholder="Find a person…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <label>
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            {(Object.keys(SORTS) as Sort[]).map((s) => (
              <option key={s} value={s}>
                {SORTS[s].label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {isLoading ? (
        <Skeleton height={200} />
      ) : isError ? (
        <p className={styles.muted}>The snapshot could not be loaded. Refresh to try again.</p>
      ) : rows.length === 0 ? (
        <p className={styles.muted}>No one matches.</p>
      ) : (
        <div className={styles.people}>
          {rows.map((r) => (
            <PersonCard key={r.person.id} row={r} />
          ))}
        </div>
      )}
    </div>
  )
}
