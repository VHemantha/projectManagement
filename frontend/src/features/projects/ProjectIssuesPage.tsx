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
  const { data: issuesPage, isLoading } = useIssues({ project: project.key, page_size: 300, ordering: 'rank' })
  const { data: board } = useProjectBoard(project.key)
  const [filters, setFilters] = useState<IssueFilters>(EMPTY_FILTERS)
  const [groupBy, setGroupBy] = useState<GroupByOption>('status')

  const issues = issuesPage?.results ?? []
  const filtered = applyIssueFilters(issues, filters)

  return (
    <div className={styles.page}>
      <IssueFilterPanel issues={issues} filters={filters} onChange={setFilters} />
      <div className={styles.main}>
        <h1 className={styles.title}>Issues</h1>
        <IssueTable
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
