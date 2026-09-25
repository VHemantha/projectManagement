import { format, formatDistanceToNow } from 'date-fns'
import { useNavigate } from 'react-router-dom'

import styles from './ProjectsListPage.module.css'
import { useProjects } from '@/api/projects'
import type { ProjectSummary } from '@/api/types'
import { Avatar } from '@/design-system'
import { type DataColumn, DataTable } from '@/features/tables/DataTable'

const EMPTY: ProjectSummary[] = []

const columns: DataColumn<ProjectSummary>[] = [
  {
    id: 'name',
    label: 'Project',
    required: true,
    size: 260,
    value: (p) => p.name,
    cell: (p) => (
      <div className={styles.projectCell}>
        <span className={styles.projectAvatar} style={{ background: p.avatar_color }}>
          {p.key.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <div className={styles.projectName}>{p.name}</div>
          <div className={styles.projectKey}>{p.key}</div>
        </div>
      </div>
    ),
  },
  { id: 'key', label: 'Key', value: (p) => p.key, defaultHidden: true, size: 120 },
  {
    id: 'project_type',
    label: 'Type',
    size: 130,
    value: (p) => (p.is_client_workspace ? 'Client jobs' : p.project_type === 'scrum' ? 'Scrum' : 'Kanban'),
    cell: (p) => (
      <span className={styles.typeBadge}>
        {p.is_client_workspace ? 'Client jobs' : p.project_type === 'scrum' ? 'Scrum' : 'Kanban'}
      </span>
    ),
  },
  { id: 'client', label: 'Client', value: (p) => p.client?.name, size: 160 },
  { id: 'team', label: 'Team', value: (p) => p.primary_team?.name, defaultHidden: true, size: 160 },
  {
    id: 'lead',
    label: 'Lead',
    size: 180,
    value: (p) => p.lead?.display_name,
    cell: (p) =>
      p.lead ? (
        <div className={styles.leadCell}>
          <Avatar name={p.lead.display_name} src={p.lead.avatar} size={24} />
          <span>{p.lead.display_name}</span>
        </div>
      ) : (
        <span style={{ color: 'var(--tf-text-subtle)' }}>Unassigned</span>
      ),
  },
  { id: 'issue_count', label: 'Jobs', value: (p) => p.issue_count, numeric: true, size: 90 },
  { id: 'description', label: 'Description', value: (p) => p.description, defaultHidden: true, size: 240 },
  {
    id: 'created_at',
    label: 'Created',
    value: (p) => p.created_at,
    cell: (p) => format(new Date(p.created_at), 'MMM d, yyyy'),
    defaultHidden: true,
    size: 130,
  },
  {
    id: 'updated_at',
    label: 'Last updated',
    value: (p) => p.updated_at,
    cell: (p) => formatDistanceToNow(new Date(p.updated_at), { addSuffix: true }),
    size: 150,
  },
]

/** The Projects section's landing pane (shown at the bare /projects route, to the right of the
 * persistent tree in ProjectsSectionLayout): every project in a customisable, sortable table. */
export function ProjectsListPage() {
  const { data: projects, isLoading } = useProjects()
  const navigate = useNavigate()

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>All projects</h1>
      </div>
      <DataTable
        tableId="projects"
        columns={columns}
        data={projects ?? EMPTY}
        getRowId={(p) => p.key}
        isLoading={isLoading}
        emptyMessage="No projects yet. Create your first one to get started."
        onRowClick={(p) => navigate(`/projects/${p.key}`)}
        exportName="projects"
        defaultSort={[{ id: 'name', desc: false }]}
        countLabel={(n) => `${n} project${n === 1 ? '' : 's'}`}
      />
    </div>
  )
}
