import { useQueryClient } from '@tanstack/react-query'
import { Home } from 'lucide-react'
import { Fragment } from 'react'
import { Link, useLocation } from 'react-router-dom'

import styles from './Breadcrumbs.module.css'
import type { TeamDetail, TeamSummary, User } from '@/api/types'

// Fixed URL segments map to a nicely-cased label. Anything not listed here is a
// dynamic value (a project key, a team/user id, an issue key) and is resolved
// separately in `resolveDynamicLabel`.
const STATIC_LABELS: Record<string, string> = {
  projects: 'Projects',
  teams: 'Teams',
  people: 'People',
  filters: 'Filters',
  dashboards: 'Dashboards',
  chat: 'Chat',
  timesheets: 'Timesheets',
  apps: 'Apps',
  profile: 'Profile',
  board: 'Board',
  backlog: 'Backlog',
  timeline: 'Timeline',
  issues: 'Issues',
  reports: 'Reports',
  settings: 'Settings',
  review: 'Review',
  epics: 'Epics',
}

interface Crumb {
  label: string
  /** Absolute path this crumb links to. The last crumb (current page) has none. */
  path: string
}

export function Breadcrumbs() {
  const location = useLocation()
  const queryClient = useQueryClient()

  const segments = location.pathname.split('/').filter(Boolean)

  // Home ("Your work") already lives behind the logo, so there's nothing useful
  // to show as a trail when we're on it.
  if (segments.length === 0) return null

  // Turn each URL segment into a crumb, resolving dynamic ids/keys to readable
  // names where we can. `prev` gives each segment its context (e.g. the id after
  // "teams" is a team, the id after "people" is a user).
  const crumbs: Crumb[] = segments.map((segment, index) => {
    const prev = segments[index - 1]
    const label = STATIC_LABELS[segment] ?? resolveDynamicLabel(queryClient, segment, prev)
    return { label, path: '/' + segments.slice(0, index + 1).join('/') }
  })

  return (
    <nav className={styles.breadcrumbs} aria-label="Breadcrumb">
      {/* Root of the trail, mirroring a file path's drive/home. */}
      <Link to="/" className={styles.crumb} aria-label="Home">
        <Home size={14} />
      </Link>

      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1
        return (
          <Fragment key={crumb.path}>
            <span className={styles.separator} aria-hidden="true">
              /
            </span>
            {isLast ? (
              // The current page is shown as plain (non-clickable) text.
              <span className={`${styles.crumb} ${styles.current}`} aria-current="page">
                {crumb.label}
              </span>
            ) : (
              <Link to={crumb.path} className={styles.crumb}>
                {crumb.label}
              </Link>
            )}
          </Fragment>
        )
      })}
    </nav>
  )
}

/**
 * Resolve a dynamic URL segment (an id or key) into a human-readable label.
 * Names are read straight from React Query's cache — by the time a detail page
 * is on screen its data is already fetched — so this stays a cheap lookup with
 * no extra network calls. When nothing is cached we fall back to the raw
 * segment so the breadcrumb still renders something meaningful.
 */
function resolveDynamicLabel(
  queryClient: ReturnType<typeof useQueryClient>,
  segment: string,
  prev: string | undefined,
): string {
  if (prev === 'projects') {
    // Match the existing design, which shows the uppercase project key (e.g. "CG").
    return segment.toUpperCase()
  }

  if (prev === 'teams') {
    const fromList = queryClient
      .getQueryData<TeamSummary[]>(['teams'])
      ?.find((team) => String(team.id) === segment)
    const fromDetail = queryClient.getQueryData<TeamDetail>(['teams', segment])
    return fromList?.name ?? fromDetail?.name ?? segment
  }

  if (prev === 'people') {
    const user = queryClient
      .getQueryData<User[]>(['users', ''])
      ?.find((u) => String(u.id) === segment)
    return user?.display_name ?? segment
  }

  // Issue keys, epic keys and anything else read fine as-is.
  return segment
}
