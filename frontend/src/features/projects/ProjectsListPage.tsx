import { createColumnHelper, useTable } from '@tanstack/react-table'
import { formatDistanceToNow } from 'date-fns'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import styles from './ProjectsListPage.module.css'
import { useProjects } from '@/api/projects'
import type { ProjectSummary } from '@/api/types'
import { tfTableFeatures } from '@/lib/tableFeatures'
import { Avatar, Skeleton } from '@/design-system'

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

/** The Projects section's landing pane (shown at the bare /projects route, to the right of the
 * persistent tree in ProjectsSectionLayout) — every project as a flat, sortable table. */
export function ProjectsListPage() {
  const { data: projects, isLoading } = useProjects()
  const navigate = useNavigate()

  const table = useTable(
    {
      features: tfTableFeatures,
      columns,
      data: projects ?? EMPTY,
    },
    (state) => ({ sorting: state.sorting }),
  )

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>All projects</h1>
      </div>

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
    </div>
  )
}
