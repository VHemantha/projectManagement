import { useQuery } from '@tanstack/react-query'

import { apiClient } from './client'
import type { TreeNode } from '@/design-system'

/** A row of the hierarchy tree: Workspace > Sub-workspace > Project. */
export interface NavTreeNode extends TreeNode {
  type: 'workspace' | 'sub_workspace' | 'project'
  project_key?: string
  team_id?: number
  client_id?: number | null
  /** /api/issues/ filters for this branch's tasks (on sub-workspaces). */
  board_query?: Record<string, string | number | boolean>
  /** The sub-workspace's list of tasks added without a project. */
  is_client_tasks?: boolean
  children: NavTreeNode[]
}

export function useNavTree(groupBy: 'hierarchy') {
  return useQuery({
    queryKey: ['reports', 'nav-tree', groupBy],
    queryFn: async () => {
      const { data } = await apiClient.get<{ group_by: string; nodes: NavTreeNode[] }>('/reports/nav-tree/', {
        params: { group_by: groupBy },
      })
      return data.nodes
    },
  })
}

export interface ProjectBudgetRow {
  project_key: string
  project_name: string
  client: string | null
  team: string | null
  lead: string | null
  is_client_jobs: boolean
  job_count: number
  open_jobs: number
  done_jobs: number
  archived_jobs: number
  budgeted_hours: number | null
  actual_hours: number
  variance_hours: number | null
  pct_complete: number | null
  job_value: string | null
  job_value_currency: string
  effective_cost: string
  margin: string | null
}

export interface IssueBudgetRow {
  issue_key: string
  summary: string
  status: string
  issue_type: string
  assignee: string | null
  due_date: string | null
  is_archived: boolean
  budgeted_hours: number | null
  actual_hours: number
  variance_hours: number | null
  allocated_value: string | null
}

export function useBudgetVsActual(projectKey?: string) {
  return useQuery({
    queryKey: ['reports', 'budget-vs-actual', projectKey ?? 'all'],
    queryFn: async () => {
      const { data } = await apiClient.get<
        { project: ProjectBudgetRow; issues: IssueBudgetRow[] } | { projects: ProjectBudgetRow[] }
      >('/reports/budget-vs-actual/', { params: projectKey ? { project: projectKey } : undefined })
      return data
    },
  })
}
