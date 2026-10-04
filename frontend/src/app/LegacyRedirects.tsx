import { Navigate, useLocation, useParams } from 'react-router-dom'

import { TeamDetailPage } from '@/features/teams/TeamDetailPage'

/* The app's hierarchy is Workspace > Sub-workspace > Project > Task. Workspaces live at
 * /workspaces/<id> and projects at /projects/<KEY>. Until Oct 2026 projects were shown as
 * "workspaces" at /workspaces/<KEY> and workspaces as "teams" at /teams/<id>, so links in
 * bookmarks, emails and chat messages use those. Project keys always start with a letter and
 * workspace ids are numbers, so an old link can always be told apart from a new one. */

const isWorkspaceId = (value: string | undefined) => !!value && /^\d+$/.test(value)

/** /workspaces/<id> is a workspace; /workspaces/<KEY>… (and /workspaces/all-issues) is an old
 * project link and goes to /projects with the rest of the path, the query and the hash. */
export function WorkspaceRoute() {
  const { teamId } = useParams<{ teamId: string }>()
  if (isWorkspaceId(teamId)) return <TeamDetailPage />
  return <LegacyWorkspacesRedirect />
}

export function LegacyWorkspacesRedirect() {
  const { pathname, search, hash } = useLocation()
  return <Navigate replace to={`${pathname.replace(/^\/workspaces(?=\/|$)/, '/projects')}${search}${hash}`} />
}

/** /teams and /teams/<id> are now /workspaces and /workspaces/<id>. */
export function LegacyTeamsRedirect() {
  const { pathname, search, hash } = useLocation()
  return <Navigate replace to={`${pathname.replace(/^\/teams(?=\/|$)/, '/workspaces')}${search}${hash}`} />
}
