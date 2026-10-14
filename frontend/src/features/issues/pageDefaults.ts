import type { CreateIssueDefaults } from '@/store/uiStore'

/** What the page being looked at says about a new task, from its address: a project's pages give
 * the project; a workspace's page, the workspace; the All-issues board, its workspace and
 * sub-workspace filters. The Create task form derives the rest. */
export function pageDefaults(pathname: string, search: string): CreateIssueDefaults {
  const params = new URLSearchParams(search)
  if (pathname.startsWith('/projects/all-issues')) {
    const team = params.get('team')
    const client = params.get('client')
    return {
      ...(team && /^\d+$/.test(team) ? { teamId: Number(team) } : {}),
      ...(client && /^\d+$/.test(client) ? { clientId: Number(client) } : {}),
    }
  }
  const project = /^\/projects\/([A-Za-z0-9]+)(?:\/|$)/.exec(pathname)
  if (project) return { projectKey: project[1] }
  const workspace = /^\/workspaces\/(\d+)(?:\/|$)/.exec(pathname)
  if (workspace) return { teamId: Number(workspace[1]) }
  return {}
}
