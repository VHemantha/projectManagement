import { Navigate, useLocation } from 'react-router-dom'

/** Old /projects/... links (bookmarks, emails, chat messages) keep working: same path and query
 * under the new /workspaces name. */
export function LegacyProjectsRedirect() {
  const { pathname, search, hash } = useLocation()
  return <Navigate replace to={`${pathname.replace(/^\/projects(?=\/|$)/, '/workspaces')}${search}${hash}`} />
}
