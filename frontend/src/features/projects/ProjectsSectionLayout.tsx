import {
  Building2,
  ChevronsLeft,
  ChevronsRight,
  ExternalLink,
  FolderKanban,
  FolderPlus,
  LayoutGrid,
  ListTodo,
  Plus,
  Search,
  UserPlus,
  Users,
} from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

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

function boardUrl(node: NavTreeNode) {
  const params = new URLSearchParams(
    Object.entries(node.board_query ?? {}).map(([k, v]) => [k, String(v)]),
  )
  return `/projects/all-issues?${params}`
}

function nodeIcon(node: TreeNode): ReactNode {
  const n = node as NavTreeNode
  if (n.type === 'workspace') return <Users size={14} aria-hidden="true" className={styles.treeIcon} />
  if (n.type === 'sub_workspace') return <Building2 size={14} aria-hidden="true" className={styles.treeIcon} />
  if (n.is_client_tasks) return <ListTodo size={14} aria-hidden="true" className={styles.treeIcon} />
  return <FolderKanban size={14} aria-hidden="true" className={styles.treeIcon} />
}

/** The Projects section: the hierarchy tree on the left —
 *
 *    Workspace > Sub-workspace > Project   (a project opens its tasks)
 *
 * — and the selected page on the right: the All tasks board (which a sub-workspace opens,
 * filtered to it), the All projects table, or a project's own tabs via ProjectLayout. */
export function ProjectsSectionLayout() {
  const navigate = useNavigate()
  const [treeSearch, setTreeSearch] = useState('')
  const [createProject, setCreateProject] = useState<Placement | null>(null)
  const [createSubWorkspace, setCreateSubWorkspace] = useState<Placement | null>(null)
  const { data: treeNodes, isLoading } = useNavTree('hierarchy')
  // Collapsed by default to an icon rail; expanded on request (remembered).
  const panel = usePanel('projectsTree')
  const [focusSearch, setFocusSearch] = useState(false)

  const handleLeafClick = (node: TreeNode) => {
    const n = node as NavTreeNode
    if (n.type === 'project' && n.project_key) navigate(`/projects/${n.project_key}`)
    // A workspace or sub-workspace with nothing in it yet has no children to expand into.
    else if (n.type === 'workspace' && typeof n.team_id === 'number') navigate(`/workspaces/${n.team_id}`)
    else if (n.type === 'sub_workspace') navigate(boardUrl(n))
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
          <Tooltip label={`All tasks in ${n.label}`} side="bottom">
            <button type="button" className={styles.rowAction} aria-label={`All tasks in ${n.label}`} onClick={() => navigate(boardUrl(n))}>
              <LayoutGrid size={13} />
            </button>
          </Tooltip>
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
          <Tooltip label="Search workspaces, sub-workspaces and projects" side="right">
            <button
              type="button"
              className={rail.button}
              onClick={() => {
                setFocusSearch(true)
                panel.setOpen(true)
              }}
              aria-label="Search workspaces, sub-workspaces and projects"
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
            Workspace › Sub-workspace › Project
          </div>

          <div className={styles.searchRow}>
            <input
              className={styles.search}
              placeholder="Search workspace, sub-workspace, project…"
              aria-label="Search workspaces, sub-workspaces and projects"
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
                nodes={treeNodes ?? []}
                onLeafClick={handleLeafClick}
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
