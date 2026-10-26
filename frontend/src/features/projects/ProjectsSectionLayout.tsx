import {
  Building2,
  ChevronsLeft,
  ChevronsRight,
  ExternalLink,
  FolderPlus,
  LayoutGrid,
  Plus,
  Search,
  UserPlus,
  Users,
} from 'lucide-react'
import { type ReactNode, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import styles from './ProjectsSectionLayout.module.css'
import { CreateClientDialog } from './CreateClientDialog'
import { CreateProjectDialog } from './CreateProjectDialog'
import { type NavTreeNode, useNavTree } from '@/api/reports'
import rail from '@/app/SideRail.module.css'
import { Button, Skeleton, Tooltip, TreeView, type TreeNode } from '@/design-system'
import { usePanel } from '@/store/sidebarStore'

/** Where a new project or sub-workspace goes when it is started from a row of the tree. */
interface Placement {
  teamId?: number
  clientId?: number
}

const TASKS_PATH = '/projects/all-issues'

/** The tasks of a tree row, keeping the view the person is on (Kanban, Tasks or Summary). */
function boardUrl(node: NavTreeNode, view?: string | null) {
  const params = new URLSearchParams(Object.entries(node.board_query ?? {}).map(([k, v]) => [k, String(v)]))
  if (view) params.set('view', view)
  return `${TASKS_PATH}?${params}`
}

/** The tree ends at the sub-workspace (AFIT, 26 Oct 2026): its projects are not listed, even
 * if an older server still sends them. */
function trimmed(nodes: NavTreeNode[]): NavTreeNode[] {
  return nodes.map((n) => ({ ...n, children: n.type === 'sub_workspace' ? [] : trimmed(n.children ?? []) }))
}

/** The row whose tasks are open: the one whose filters are exactly the page's. */
function selectedNode(nodes: NavTreeNode[], search: string): string | null {
  const params = new URLSearchParams(search)
  params.delete('view')
  const key = (entries: [string, string][]) => entries.map(([k, v]) => `${k}=${v}`).sort().join('&')
  const wanted = key([...params.entries()])
  if (!wanted) return null
  const walk = (list: NavTreeNode[]): string | null => {
    for (const n of list) {
      if (n.board_query && key(Object.entries(n.board_query).map(([k, v]) => [k, String(v)])) === wanted) return n.id
      const inner = walk(n.children ?? [])
      if (inner) return inner
    }
    return null
  }
  return walk(nodes)
}

function nodeIcon(node: TreeNode): ReactNode {
  const n = node as NavTreeNode
  if (n.type === 'workspace') return <Users size={14} aria-hidden="true" className={styles.treeIcon} />
  return <Building2 size={14} aria-hidden="true" className={styles.treeIcon} />
}

/** The Projects section: the hierarchy tree on the left —
 *
 *    Workspace > Sub-workspace   (each opens its tasks)
 *
 * — and the selected page on the right: the tasks of the selected workspace or sub-workspace
 * (Kanban, task list and summary, filtered to it), the All projects table, or a project's own
 * tabs via ProjectLayout. */
export function ProjectsSectionLayout() {
  const navigate = useNavigate()
  const [treeSearch, setTreeSearch] = useState('')
  const [createProject, setCreateProject] = useState<Placement | null>(null)
  const [createSubWorkspace, setCreateSubWorkspace] = useState<Placement | null>(null)
  const { data: rawNodes, isLoading } = useNavTree('hierarchy')
  const treeNodes = useMemo(() => trimmed(rawNodes ?? []), [rawNodes])
  const location = useLocation()
  const onTasks = location.pathname === TASKS_PATH
  const view = onTasks ? new URLSearchParams(location.search).get('view') : null
  const selectedId = onTasks ? selectedNode(treeNodes, location.search) : null
  // Collapsed by default to an icon rail; expanded on request (remembered).
  const panel = usePanel('projectsTree')
  const [focusSearch, setFocusSearch] = useState(false)

  // A workspace or a sub-workspace opens its tasks, filtered to it (a workspace also expands).
  const openNode = (node: TreeNode) => {
    const n = node as NavTreeNode
    if (n.board_query) navigate(boardUrl(n, view))
    else if (n.type === 'workspace' && typeof n.team_id === 'number') navigate(boardUrl({ ...n, board_query: { team: n.team_id } }, view))
  }

  const rowActions = (node: TreeNode): ReactNode => {
    const n = node as NavTreeNode
    if (n.type === 'workspace' && typeof n.team_id === 'number') {
      return (
        <>
          <Tooltip label={`New sub-workspace in ${n.label}`} side="bottom">
            <button type="button" className={styles.rowAction} aria-label={`New sub-workspace in ${n.label}`} onClick={() => setCreateSubWorkspace({ teamId: n.team_id })}>
              <Plus size={13} />
            </button>
          </Tooltip>
          <Tooltip label={`Open ${n.label}`} side="bottom">
            <button type="button" className={styles.rowAction} aria-label={`Open ${n.label}`} onClick={() => navigate(`/workspaces/${n.team_id}`)}>
              <ExternalLink size={13} />
            </button>
          </Tooltip>
        </>
      )
    }
    if (n.type === 'sub_workspace') {
      return (
        <>
          {typeof n.client_id === 'number' && (
            <Tooltip label={`New project in ${n.label}`} side="bottom">
              <button
                type="button"
                className={styles.rowAction}
                aria-label={`New project in ${n.label}`}
                onClick={() => setCreateProject({ clientId: n.client_id ?? undefined })}
              >
                <Plus size={13} />
              </button>
            </Tooltip>
          )}
        </>
      )
    }
    return null
  }

  return (
    <div className={styles.layout}>
      {!panel.open ? (
        <aside className={rail.rail} aria-label="Projects panel (collapsed)">
          <Tooltip label="Expand projects panel" side="right">
            <button type="button" className={rail.toggle} onClick={panel.toggle} aria-label="Expand projects panel">
              <ChevronsRight size={18} />
            </button>
          </Tooltip>
          <Tooltip label="Create project" side="right">
            <button type="button" className={rail.button} onClick={() => setCreateProject({})} aria-label="Create project">
              <FolderPlus size={18} />
            </button>
          </Tooltip>
          <Tooltip label="All tasks board" side="right">
            <NavLink to="/projects/all-issues" className={rail.button} aria-label="All tasks board">
              <LayoutGrid size={18} />
            </NavLink>
          </Tooltip>
          <span className={rail.divider} />
          <Tooltip label="Browse workspaces" side="right">
            <button type="button" className={rail.button} onClick={panel.toggle} aria-label="Browse workspaces">
              <Users size={18} />
            </button>
          </Tooltip>
          <Tooltip label="Search workspaces and sub-workspaces" side="right">
            <button
              type="button"
              className={rail.button}
              onClick={() => {
                setFocusSearch(true)
                panel.setOpen(true)
              }}
              aria-label="Search workspaces and sub-workspaces"
            >
              <Search size={18} />
            </button>
          </Tooltip>
          <Tooltip label="New sub-workspace" side="right">
            <button type="button" className={rail.button} onClick={() => setCreateSubWorkspace({})} aria-label="New sub-workspace">
              <UserPlus size={18} />
            </button>
          </Tooltip>
        </aside>
      ) : (
        <aside className={styles.sidebar} aria-label="Projects panel">
          <div className={styles.sidebarHeader}>
            <span className={styles.sidebarTitle}>Projects</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <Button variant="primary" size="sm" onClick={() => setCreateProject({})}>
                <Plus size={14} /> Create
              </Button>
              <Tooltip label="Collapse panel" side="bottom">
                <button type="button" className={rail.toggle} onClick={panel.toggle} aria-label="Collapse projects panel">
                  <ChevronsLeft size={18} />
                </button>
              </Tooltip>
            </div>
          </div>

          <NavLink
            to="/projects/all-issues"
            className={({ isActive }) => `${styles.allIssuesLink} ${isActive ? styles.allIssuesLinkActive : ''}`}
          >
            <LayoutGrid size={14} /> All tasks board
          </NavLink>

          <div className={styles.hierarchyHint} aria-hidden="true">
            Workspace › Sub-workspace
          </div>

          <div className={styles.searchRow}>
            <input
              className={styles.search}
              placeholder="Search workspace, sub-workspace…"
              aria-label="Search workspaces and sub-workspaces"
              value={treeSearch}
              autoFocus={focusSearch}
              onBlur={() => setFocusSearch(false)}
              onChange={(e) => setTreeSearch(e.target.value)}
            />
            <Button variant="secondary" size="sm" onClick={() => setCreateSubWorkspace({})} aria-label="New sub-workspace">
              <Plus size={14} />
            </Button>
          </div>

          <div className={styles.tree}>
            {isLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 12 }}>
                {[0, 1, 2].map((row) => (
                  <Skeleton key={row} height={13} width={row % 2 === 0 ? '60%' : '40%'} />
                ))}
              </div>
            ) : (
              <TreeView
                nodes={treeNodes}
                onLeafClick={openNode}
                onBranchClick={openNode}
                selectedId={selectedId}
                filterQuery={treeSearch}
                renderIcon={nodeIcon}
                renderActions={rowActions}
                emptyMessage="No workspaces yet."
              />
            )}
          </div>
        </aside>
      )}

      <div className={styles.content}>
        <Outlet />
      </div>

      <CreateProjectDialog
        open={createProject !== null}
        onOpenChange={(open) => !open && setCreateProject(null)}
        defaultTeamId={createProject?.teamId}
        defaultClientId={createProject?.clientId}
      />
      <CreateClientDialog
        open={createSubWorkspace !== null}
        onOpenChange={(open) => !open && setCreateSubWorkspace(null)}
        defaultTeamId={createSubWorkspace?.teamId}
      />
    </div>
  )
}
