import {
  Building2,
  ChevronsLeft,
  ChevronsRight,
  FolderPlus,
  Layers,
  LayoutGrid,
  Plus,
  Search,
  UserPlus,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import styles from './ProjectsSectionLayout.module.css'
import { CreateClientDialog } from './CreateClientDialog'
import { CreateProjectDialog } from './CreateProjectDialog'
import { useNavTree } from '@/api/reports'
import rail from '@/app/SideRail.module.css'
import { Button, Skeleton, Tooltip, TreeView, type TreeNode } from '@/design-system'
import { usePanel } from '@/store/sidebarStore'

type TreeMode = 'group' | 'team' | 'client'

const TREE_MODES: [TreeMode, string][] = [
  ['group', 'Group'],
  ['team', 'Team'],
  ['client', 'Client'],
]

const TREE_MODE_ICONS: Record<TreeMode, LucideIcon> = { group: Layers, team: Users, client: Building2 }

const TREE_EMPTY_MESSAGE: Record<TreeMode, string> = {
  group: 'No groups yet.',
  team: 'No teams yet.',
  client: 'No clients yet.',
}

/** Persistent Group/Team -> Client tree on the left; the right side shows the selected page —
 * the All issues board (which a client leaf opens, filtered to that branch), the All projects
 * table, or a project's own tabs via ProjectLayout. Mirrors Chat's channel-list/thread-pane
 * split so browsing to a client's work and seeing its cards happens in one continuous page. */
export function ProjectsSectionLayout() {
  const navigate = useNavigate()
  const [treeMode, setTreeMode] = useState<TreeMode>('group')
  const [treeSearch, setTreeSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [createClientOpen, setCreateClientOpen] = useState(false)
  const { data: treeNodes, isLoading } = useNavTree(treeMode)
  // Collapsed by default to an icon rail; expanded on request (remembered).
  const panel = usePanel('projectsTree')
  const [focusSearch, setFocusSearch] = useState(false)
  const openInMode = (mode: TreeMode) => {
    setTreeMode(mode)
    panel.setOpen(true)
  }

  const handleTreeLeafClick = (node: TreeNode) => {
    // The tree stops at clients: a client opens the All issues board filtered to its branch.
    // board_query uses the /api/issues/ filter names, which the board reads from its URL.
    if (node.type === 'client' && node.board_query && typeof node.board_query === 'object') {
      const params = new URLSearchParams(
        Object.entries(node.board_query as Record<string, string | number | boolean>).map(([k, v]) => [k, String(v)]),
      )
      navigate(`/workspaces/all-issues?${params}`)
    }
    // A team/group with no projects yet has no children to expand into, so TreeView treats it
    // as a leaf too — send it to the team's own detail page instead of doing nothing.
    if ((node.type === 'team' || node.type === 'group') && typeof node.team_id === 'number') {
      navigate(`/teams/${node.team_id}`)
    }
  }

  return (
    <div className={styles.layout}>
      {!panel.open ? (
        <aside className={rail.rail} aria-label="Workspaces panel (collapsed)">
          <Tooltip label="Expand workspaces panel" side="right">
            <button type="button" className={rail.toggle} onClick={panel.toggle} aria-label="Expand workspaces panel">
              <ChevronsRight size={18} />
            </button>
          </Tooltip>
          <Tooltip label="Create workspace" side="right">
            <button type="button" className={rail.button} onClick={() => setCreateOpen(true)} aria-label="Create workspace">
              <FolderPlus size={18} />
            </button>
          </Tooltip>
          <Tooltip label="All jobs board" side="right">
            <NavLink to="/workspaces/all-issues" className={rail.button} aria-label="All jobs board">
              <LayoutGrid size={18} />
            </NavLink>
          </Tooltip>
          <span className={rail.divider} />
          {TREE_MODES.map(([mode, label]) => {
            const Icon = TREE_MODE_ICONS[mode]
            return (
              <Tooltip key={mode} label={`Browse by ${label.toLowerCase()}`} side="right">
                <button
                  type="button"
                  className={rail.button}
                  data-active={treeMode === mode}
                  onClick={() => openInMode(mode)}
                  aria-label={`Browse by ${label.toLowerCase()}`}
                >
                  <Icon size={18} />
                </button>
              </Tooltip>
            )
          })}
          <Tooltip label="Search teams and clients" side="right">
            <button
              type="button"
              className={rail.button}
              onClick={() => {
                setFocusSearch(true)
                panel.setOpen(true)
              }}
              aria-label="Search teams and clients"
            >
              <Search size={18} />
            </button>
          </Tooltip>
          <Tooltip label="New client" side="right">
            <button type="button" className={rail.button} onClick={() => setCreateClientOpen(true)} aria-label="New client">
              <UserPlus size={18} />
            </button>
          </Tooltip>
        </aside>
      ) : (
      <aside className={styles.sidebar} aria-label="Workspaces panel">
        <div className={styles.sidebarHeader}>
          <span className={styles.sidebarTitle}>Workspaces</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus size={14} /> Create
            </Button>
            <Tooltip label="Collapse panel" side="bottom">
              <button type="button" className={rail.toggle} onClick={panel.toggle} aria-label="Collapse workspaces panel">
                <ChevronsLeft size={18} />
              </button>
            </Tooltip>
          </div>
        </div>

        <NavLink
          to="/workspaces/all-issues"
          className={({ isActive }) => `${styles.allIssuesLink} ${isActive ? styles.allIssuesLinkActive : ''}`}
        >
          <LayoutGrid size={14} /> All jobs board
        </NavLink>

        <div className={styles.modeRow}>
          {TREE_MODES.map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              className={styles.modeBtn}
              data-active={treeMode === mode}
              onClick={() => setTreeMode(mode)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className={styles.searchRow}>
          <input
            className={styles.search}
            placeholder="Search team, client…"
            aria-label="Search teams and clients"
            value={treeSearch}
            autoFocus={focusSearch}
            onBlur={() => setFocusSearch(false)}
            onChange={(e) => setTreeSearch(e.target.value)}
          />
          <Button variant="secondary" size="sm" onClick={() => setCreateClientOpen(true)} aria-label="New client">
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
              onLeafClick={handleTreeLeafClick}
              filterQuery={treeSearch}
              emptyMessage={TREE_EMPTY_MESSAGE[treeMode]}
            />
          )}
        </div>
      </aside>
      )}

      <div className={styles.content}>
        <Outlet />
      </div>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
      <CreateClientDialog open={createClientOpen} onOpenChange={setCreateClientOpen} />
    </div>
  )
}
