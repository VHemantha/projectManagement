import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import styles from './AllIssuesBoardPage.module.css'
import { CATEGORY_COLUMNS } from './categoryColumns'
import { KanbanBoard } from './KanbanBoard'
import { useClients } from '@/api/clients'
import { useIssues, useMoveIssue } from '@/api/issues'
import { useCategoryStatusMaps } from '@/api/projects'
import { useTeams } from '@/api/teams'

const PAGE_SIZE = 300

/** Cross-project board in the Projects section: every project's issues, narrowed by Team
 * (a team's own + contributing projects; a Group also covers its sub-teams, like the tree) and
 * by Client. Columns are status categories because each project has its own workflow — the
 * same approach as the Team board. The filters live in the URL so a filtered view can be
 * bookmarked or shared. */
export function AllIssuesBoardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const teamId = searchParams.get('team') ?? ''
  const clientId = searchParams.get('client') ?? ''
  const { data: teams } = useTeams()
  const { data: clients } = useClients()
  const moveIssue = useMoveIssue()

  const setFilter = (name: 'team' | 'client', value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(name, value)
    else next.delete(name)
    setSearchParams(next, { replace: true })
  }

  const { data: issuesPage, isLoading } = useIssues({
    ...(teamId ? { team: Number(teamId) } : {}),
    ...(clientId ? { client: Number(clientId) } : {}),
    no_parent: true,
    exclude_type: 'Epic',
    page_size: PAGE_SIZE,
    ordering: 'rank',
  })
  const issues = useMemo(() => issuesPage?.results ?? [], [issuesPage])
  const total = issuesPage?.count ?? 0

  const projectKeys = useMemo(() => [...new Set(issues.map((i) => i.project_key))], [issues])
  const { maps } = useCategoryStatusMaps(projectKeys)

  // Groups first, each followed by its sub-teams, so the dropdown reads like the tree.
  const teamOptions = useMemo(() => {
    const all = teams ?? []
    const groups = all.filter((t) => !t.parent)
    const ordered = groups.flatMap((g) => [
      { team: g, depth: 0 },
      ...all.filter((t) => t.parent?.id === g.id).map((t) => ({ team: t, depth: 1 })),
    ])
    const placed = new Set(ordered.map((o) => o.team.id))
    return [...ordered, ...all.filter((t) => !placed.has(t.id)).map((t) => ({ team: t, depth: 1 }))]
  }, [teams])

  const filtersActive = !!teamId || !!clientId

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>All issues board</h1>
        <div className={styles.filters}>
          <label className={styles.filter}>
            <span className={styles.filterLabel}>Team</span>
            <select
              className={styles.select}
              value={teamId}
              onChange={(e) => setFilter('team', e.target.value)}
              aria-label="Filter by team"
            >
              <option value="">Any team</option>
              {teamOptions.map(({ team, depth }) => (
                <option key={team.id} value={team.id}>
                  {depth ? `   ${team.name}` : team.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.filter}>
            <span className={styles.filterLabel}>Client</span>
            <select
              className={styles.select}
              value={clientId}
              onChange={(e) => setFilter('client', e.target.value)}
              aria-label="Filter by client"
            >
              <option value="">Any client</option>
              {clients?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          {filtersActive && (
            <button type="button" className={styles.clear} onClick={() => setSearchParams({}, { replace: true })}>
              Clear filters
            </button>
          )}
          {!isLoading && (
            <span className={styles.count}>
              {total > issues.length
                ? `Showing ${issues.length} of ${total} issues`
                : `${total} issue${total === 1 ? '' : 's'}`}
            </span>
          )}
        </div>
      </div>
      <div className={styles.board}>
        <KanbanBoard
          issues={issues}
          columns={CATEGORY_COLUMNS}
          isLoading={isLoading}
          defaultSwimlaneMode="project"
          availableSwimlanes={['none', 'project', 'assignee']}
          emptyMessage={filtersActive ? 'No issues match this team/client.' : 'No issues yet.'}
          onMoveIssue={({ issue, column, beforeId, afterId }) => {
            const statusId = column.category ? maps[issue.project_key]?.[column.category] : undefined
            moveIssue.mutate({ key: issue.key, status_id: statusId, before_id: beforeId, after_id: afterId })
          }}
        />
      </div>
    </div>
  )
}
