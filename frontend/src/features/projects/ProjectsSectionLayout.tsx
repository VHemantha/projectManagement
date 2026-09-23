import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'

import styles from './ProjectsSectionLayout.module.css'
import { CreateClientDialog } from './CreateClientDialog'
import { CreateProjectDialog } from './CreateProjectDialog'
import { useNavTree } from '@/api/reports'
import { Button, Skeleton, TreeView, type TreeNode } from '@/design-system'

type TreeMode = 'group' | 'team' | 'client'

const TREE_MODES: [TreeMode, string][] = [
  ['group', 'Group'],
  ['team', 'Team'],
  ['client', 'Client'],
]

const TREE_EMPTY_MESSAGE: Record<TreeMode, string> = {
  group: 'No groups yet.',
  team: 'No teams yet.',
  client: 'No clients yet.',
}

/** Persistent Group -> Client -> Project/Board tree on the left, selected project's own tab
 * content (Board/Backlog/Issues/Timeline/Reports/Settings, via the existing ProjectLayout and
 * every existing per-tab page, unchanged) on the right — mirrors Chat's channel-list/thread-pane
 * split so browsing to a client's work and opening its board happens in one continuous page. */
export function ProjectsSectionLayout() {
  const navigate = useNavigate()
  const [treeMode, setTreeMode] = useState<TreeMode>('group')
  const [treeSearch, setTreeSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [createClientOpen, setCreateClientOpen] = useState(false)
  const { data: treeNodes, isLoading } = useNavTree(treeMode)

  const handleTreeLeafClick = (node: TreeNode) => {
    if (node.type === 'board' && typeof node.project_key === 'string') navigate(`/projects/${node.project_key}/board`)
    else if (node.type === 'project' && typeof node.key === 'string') navigate(`/projects/${node.key}`)
    // A team/group with no projects yet has no children to expand into, so TreeView treats it
    // as a leaf too — send it to the team's own detail page instead of doing nothing.
    else if ((node.type === 'team' || node.type === 'group') && typeof node.team_id === 'number') {
      navigate(`/teams/${node.team_id}`)
    }
  }

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <span className={styles.sidebarTitle}>Projects</span>
          <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
            <Plus size={14} /> Create
          </Button>
        </div>

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
            placeholder="Search team, client, project…"
            value={treeSearch}
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

      <div className={styles.content}>
        <Outlet />
      </div>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
      <CreateClientDialog open={createClientOpen} onOpenChange={setCreateClientOpen} />
    </div>
  )
}
