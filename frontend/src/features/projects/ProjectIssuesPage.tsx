import { useState } from 'react'

import styles from './ProjectIssuesPage.module.css'
import { useProjectContext } from './useProjectContext'
import { useIssues } from '@/api/issues'
import { useProjectBoard } from '@/api/projects'
import { EMPTY_FILTERS, IssueFilterPanel, type IssueFilters, applyIssueFilters } from '@/features/tables/IssueFilterPanel'
import { IssueTable } from '@/features/tables/IssueTable'
import type { GroupByOption } from '@/features/tables/IssueTable'

export function ProjectIssuesPage() {
  const { project } = useProjectContext()
  const [showArchived, setShowArchived] = useState(false)
  const { data: issuesPage, isLoading } = useIssues({
    project: project.key,
    page_size: 300,
    ordering: 'rank',
    ...(showArchived ? { include_archived: true } : {}),
  })
  const { data: board } = useProjectBoard(project.key)
  const [filters, setFilters] = useState<IssueFilters>(EMPTY_FILTERS)
  const [groupBy, setGroupBy] = useState<GroupByOption>('status')

  const issues = issuesPage?.results ?? []
  const filtered = applyIssueFilters(issues, filters)

  return (
    <div className={styles.page}>
      <IssueFilterPanel issues={issues} filters={filters} onChange={setFilters} />
      <div className={styles.main}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>Jobs</h1>
          <label className={styles.archivedToggle}>
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            Show archived
          </label>
        </div>
        <IssueTable
          tableId="project-jobs"
          selectable
          issues={filtered}
          isLoading={isLoading}
          groupBy={groupBy}
          onGroupByChange={setGroupBy}
          availableGroupBy={['none', 'status', 'assignee']}
          projectStatuses={board?.statuses}
        />
      </div>
    </div>
  )
}
