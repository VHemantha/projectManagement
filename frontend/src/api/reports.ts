import { useQuery } from '@tanstack/react-query'

import { apiClient } from './client'
import type { TreeNode } from '@/design-system'

export interface NavTreeNode extends TreeNode {
  type: 'team' | 'client' | 'project' | 'board'
  key?: string
  board_id?: number
  project_key?: string
  children: NavTreeNode[]
}

export function useNavTree(groupBy: 'team' | 'client') {
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
