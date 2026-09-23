import { createColumnHelper, useTable } from '@tanstack/react-table'
import { formatDistanceToNow } from 'date-fns'
import { ArrowDown, ArrowUp, ArrowUpDown, Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import styles from './ProjectsListPage.module.css'
import { CreateClientDialog } from './CreateClientDialog'
import { CreateProjectDialog } from './CreateProjectDialog'
import { useNavTree } from '@/api/reports'
import { useProjects } from '@/api/projects'
import type { ProjectSummary } from '@/api/types'
import { tfTableFeatures } from '@/lib/tableFeatures'
import { Avatar, Button, Skeleton, TreeView, type TreeNode } from '@/design-system'

const EMPTY: ProjectSummary[] = []
const helper = createColumnHelper<typeof tfTableFeatures, ProjectSummary>()

const columns = helper.columns([
  helper.accessor('name', {
    header: 'Project',
    sortFn: 'alphanumeric',
    cell: (ctx) => {
      const project = ctx.row.original
      return (
        <div className={styles.projectCell}>
          <span className={styles.projectAvatar} style={{ background: project.avatar_color }}>
            {project.key.slice(0, 2)}
          </span>
          <div>
            <div className={styles.projectName}>{project.name}</div>
            <div className={styles.projectKey}>{project.key}</div>
          </div>
        </div>
      )
    },
  }),
  helper.accessor('project_type', {
    header: 'Type',
    sortFn: 'alphanumeric',
    cell: (ctx) => <span className={styles.typeBadge}>{ctx.getValue()}</span>,
  }),
  helper.accessor((row) => row.lead?.display_name ?? '', {
    id: 'lead',
    header: 'Lead',
    sortFn: 'alphanumeric',
    cell: (ctx) => {
      const lead = ctx.row.original.lead
      if (!lead) return <span style={{ color: 'var(--tf-text-subtle)' }}>Unassigned</span>
      return (
        <div className={styles.leadCell}>
          <Avatar name={lead.display_name} src={lead.avatar} size={24} />
          <span>{lead.display_name}</span>
        </div>
      )
    },
  }),
  helper.accessor('issue_count', { header: 'Issues', sortFn: 'alphanumeric' }),
  helper.accessor('updated_at', {
    header: 'Last updated',
    sortFn: 'alphanumeric',
    cell: (ctx) => formatDistanceToNow(new Date(ctx.getValue()), { addSuffix: true }),
  }),
])

type ViewMode = 'flat' | 'group' | 'team' | 'client'

const TREE_EMPTY_MESSAGE: Record<Exclude<ViewMode, 'flat'>, string> = {
  group: 'No groups yet.',
  team: 'No teams yet.',
  client: 'No clients yet.',
}

export function ProjectsListPage() {
  const { data: projects, isLoading } = useProjects()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = useState(false)
  const [createClientOpen, setCreateClientOpen] = useState(false)
  // "By Group" first — that's the primary way the org browses work day-to-day.
  const [viewMode, setViewMode] = useState<ViewMode>('group')
  const [treeSearch, setTreeSearch] = useState('')
  const { data: treeNodes, isLoading: treeLoading } = useNavTree(viewMode === 'flat' ? 'group' : viewMode)

  const table = useTable(
    {
      features: tfTableFeatures,
      columns,
      data: projects ?? EMPTY,
    },
    (state) => ({ sorting: state.sorting }),
  )

  const handleTreeLeafClick = (node: TreeNode) => {
    if (node.type === 'board' && typeof node.project_key === 'string') navigate(`/projects/${node.project_key}/board`)
    else if (node.type === 'project' && typeof node.key === 'string') navigate(`/projects/${node.key}`)
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Projects</h1>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus size={16} /> Create project
        </Button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <div style={{ display: 'inline-flex', border: '1px solid var(--tf-border)', borderRadius: 6, overflow: 'hidden' }}>
          {([
            ['flat', 'Flat'],
            ['group', 'By Group'],
            ['team', 'By Team'],
            ['client', 'By Client'],
          ] as const).map(([mode, label]) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                fontSize: 13,
                padding: '6px 14px',
                border: 'none',
                cursor: 'pointer',
                background: viewMode === mode ? 'var(--tf-blue-subtle)' : 'var(--tf-surface)',
                color: viewMode === mode ? 'var(--tf-blue)' : 'var(--tf-text)',
                fontWeight: viewMode === mode ? 600 : 400,
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {viewMode !== 'flat' && (
          <input
            placeholder="Search team, client, project or board…"
            value={treeSearch}
            onChange={(e) => setTreeSearch(e.target.value)}
            style={{
              flex: 1,
              maxWidth: 320,
              height: 32,
              borderRadius: 6,
              border: '1px solid var(--tf-border)',
              padding: '0 10px',
              fontSize: 13,
            }}
          />
        )}
        {viewMode !== 'flat' && (
          <Button variant="secondary" size="sm" onClick={() => setCreateClientOpen(true)}>
            <Plus size={14} /> New client
          </Button>
        )}
      </div>

      {viewMode !== 'flat' ? (
        <div className={styles.tableWrap} style={{ padding: 8 }}>
          {treeLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 8 }}>
              {[0, 1, 2].map((row) => (
                <Skeleton key={row} height={13} width={row % 2 === 0 ? '50%' : '35%'} />
              ))}
            </div>
          ) : (
            <TreeView
              nodes={treeNodes ?? []}
              onLeafClick={handleTreeLeafClick}
              filterQuery={treeSearch}
              emptyMessage={TREE_EMPTY_MESSAGE[viewMode as Exclude<ViewMode, 'flat'>]}
            />
          )}
        </div>
      ) : (
      <div className={styles.tableWrap}>
        {isLoading ? (
          <div style={{ padding: 'var(--tf-space-3) var(--tf-space-4)' }}>
            {[0, 1, 2, 3].map((row) => (
              <div key={row} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '10px 0' }}>
                <Skeleton width={32} height={32} style={{ borderRadius: 4 }} />
                <Skeleton width="30%" height={12} />
                <Skeleton width={80} height={12} />
                <Skeleton width={120} height={12} />
              </div>
            ))}
          </div>
        ) : !projects || projects.length === 0 ? (
          <div className={styles.empty}>No projects yet. Create your first one to get started.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => {
                    const sorted = header.column.getIsSorted()
                    return (
                      <th key={header.id} onClick={header.column.getToggleSortingHandler()}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <table.FlexRender header={header} />
                          {sorted === 'asc' && <ArrowUp size={12} />}
                          {sorted === 'desc' && <ArrowDown size={12} />}
                          {!sorted && <ArrowUpDown size={12} style={{ opacity: 0.3 }} />}
                        </span>
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} onClick={() => navigate(`/projects/${row.original.key}`)}>
                  {row.getAllCells().map((cell) => (
                    <td key={cell.id}>
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      )}

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
      <CreateClientDialog open={createClientOpen} onOpenChange={setCreateClientOpen} />
    </div>
  )
}
