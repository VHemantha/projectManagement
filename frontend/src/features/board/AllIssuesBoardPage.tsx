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
const NONE = 'none'

/** Cross-project board in the Projects section: every project's issues, narrowed by Team
 * (a team's own + contributing projects; a Group also covers its sub-teams, like the tree) and
 * by Client. Columns are status categories because each project has its own workflow — the
 * same approach as the Team board. The filters live in the URL (using the /api/issues/ filter
 * names), so a filtered view can be bookmarked or shared and the Projects tree's client leaves
 * can link straight to it. */
export function AllIssuesBoardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const teamId = searchParams.get('team') ?? ''
  const clientId = searchParams.get('client') ?? ''
  const noTeam = searchParams.get('no_team') === 'true'
  const noClient = searchParams.get('no_client') === 'true'
  // Set by the tree's Team mode: that team's own projects only, not its sub-teams'.
  const excludeSubTeams = searchParams.get('exclude_sub_teams') === 'true'
  const { data: teams } = useTeams()
  const { data: clients } = useClients()
  const moveIssue = useMoveIssue()

  // value: '' (any), NONE, or an id. Picking from a dropdown replaces everything the tree may
  // have set for that dimension, including exclude_sub_teams.
  const setFilter = (name: 'team' | 'client', value: string) => {
    const next = new URLSearchParams(searchParams)
    next.delete(name)
    next.delete(`no_${name}`)
    if (name === 'team') next.delete('exclude_sub_teams')
    if (value === NONE) next.set(`no_${name}`, 'true')
    else if (value) next.set(name, value)
    setSearchParams(next, { replace: true })
  }

  const { data: issuesPage, isLoading } = useIssues({
    ...(noTeam ? { no_team: true } : teamId ? { team: Number(teamId), exclude_sub_teams: excludeSubTeams || undefined } : {}),
    ...(noClient ? { no_client: true } : clientId ? { client: Number(clientId) } : {}),
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

  const teamValue = noTeam ? NONE : teamId
  const clientValue = noClient ? NONE : clientId
  const filtersActive = !!teamValue || !!clientValue
  const selectedHasSubTeams = !!teamId && (teams ?? []).some((t) => String(t.parent?.id) === teamId)

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>All issues board</h1>
        <div className={styles.filters}>
          <label className={styles.filter}>
            <span className={styles.filterLabel}>Team</span>
            <select
              className={styles.select}
              value={teamValue}
              onChange={(e) => setFilter('team', e.target.value)}
              aria-label="Filter by team"
            >
              <option value="">Any team</option>
              <option value={NONE}>No team</option>
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
              value={clientValue}
              onChange={(e) => setFilter('client', e.target.value)}
              aria-label="Filter by client"
            >
              <option value="">Any client</option>
              <option value={NONE}>No client (internal)</option>
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
              {excludeSubTeams && selectedHasSubTeams && ' · excluding sub-teams'}
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
