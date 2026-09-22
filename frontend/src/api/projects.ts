import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Board, Paginated, ProjectDetail, ProjectMembership, ProjectSummary, ProjectType } from './types'

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<ProjectSummary>>('/projects/')
      return data.results
    },
  })
}

export function useProject(key: string | undefined) {
  return useQuery({
    queryKey: ['projects', key],
    enabled: !!key,
    queryFn: async () => {
      const { data } = await apiClient.get<ProjectDetail>(`/projects/${key}/`)
      return data
    },
  })
}

export function useProjectBoard(key: string | undefined) {
  return useQuery({
    queryKey: ['projects', key, 'board'],
    enabled: !!key,
    queryFn: async () => {
      const { data } = await apiClient.get<Board>(`/projects/${key}/board/`)
      return data
    },
  })
}

/** Resolves, per project, the first status id in each category (todo/in_progress/done).
 * Used by cross-project boards (Team, My Work) to translate a "category" column drop
 * into the correct concrete status for whichever project the dragged issue belongs to. */
export function useCategoryStatusMaps(projectKeys: string[]) {
  const results = useQueries({
    queries: projectKeys.map((key) => ({
      queryKey: ['projects', key, 'board'],
      queryFn: async () => {
        const { data } = await apiClient.get<Board>(`/projects/${key}/board/`)
        return data
      },
      staleTime: 5 * 60 * 1000,
    })),
  })

  const maps: Record<string, Record<string, number>> = {}
  projectKeys.forEach((key, i) => {
    const board = results[i]?.data
    if (!board) return
    const byCategory: Record<string, number> = {}
    for (const status of board.statuses) {
      if (!(status.category in byCategory)) byCategory[status.category] = status.id
    }
    maps[key] = byCategory
  })
  return { maps, isLoading: results.some((r) => r.isLoading) }
}

export interface CreateProjectPayload {
  key: string
  name: string
  description?: string
  project_type: ProjectType
  lead_id?: number
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CreateProjectPayload) => {
      const { data } = await apiClient.post<ProjectDetail>('/projects/', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export interface UpdateProjectPayload {
  name?: string
  description?: string
  lead_id?: number
  client_id?: number | null
  primary_team_id?: number | null
  contributing_team_ids?: number[]
  budgeted_hours?: number | null
  job_value?: string | null
  job_value_currency?: string
}

export function useUpdateProject(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: UpdateProjectPayload) => {
      const { data } = await apiClient.patch<ProjectDetail>(`/projects/${key}/`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects', key] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      // Client/team assignment changes the tree-nav view's shape.
      queryClient.invalidateQueries({ queryKey: ['reports', 'nav-tree'] })
    },
  })
}

function useInvalidateMembers(key: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['projects', key] })
}

export function useAddMember(key: string) {
  const invalidate = useInvalidateMembers(key)
  return useMutation({
    mutationFn: async (payload: { user_id: number; role: string }) => {
      const { data } = await apiClient.post<ProjectMembership>(`/projects/${key}/members/`, payload)
      return data
    },
    onSuccess: invalidate,
  })
}

export function useUpdateMemberRole(key: string) {
  const invalidate = useInvalidateMembers(key)
  return useMutation({
    mutationFn: async ({ id, role }: { id: number; role: string }) => {
      const { data } = await apiClient.patch<ProjectMembership>(`/projects/${key}/members/${id}/`, { role })
      return data
    },
    onSuccess: invalidate,
  })
}

export function useRemoveMember(key: string) {
  const invalidate = useInvalidateMembers(key)
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/projects/${key}/members/${id}/`)
    },
    onSuccess: invalidate,
  })
}
