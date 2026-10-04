import { type UseQueryResult, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { apiClient } from './client'
import type { Board, Label, Paginated, ProjectDetail, ProjectMembership, ProjectSummary, ProjectType } from './types'

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

/** Several projects' boards at once (same cache entries as useProjectBoard), for boards that
 * mix projects (Team, My Work, All issues) and need each card's own project settings. */
export function useProjectBoards(projectKeys: string[]) {
  // A stable `combine` (it only depends on the keys) keeps the returned object — and so
  // anything memoised on it — stable until a board actually changes. Pass memoised keys.
  const combine = useCallback(
    (results: UseQueryResult<Board>[]) => {
      const boards: Record<string, Board> = {}
      results.forEach((r, i) => {
        if (r.data) boards[projectKeys[i]] = r.data
      })
      return { boards, isLoading: results.some((r) => r.isLoading) }
    },
    [projectKeys],
  )
  return useQueries({
    queries: projectKeys.map((key) => ({
      queryKey: ['projects', key, 'board'],
      queryFn: async () => {
        const { data } = await apiClient.get<Board>(`/projects/${key}/board/`)
        return data
      },
    })),
    combine,
  })
}

export interface CreateProjectPayload {
  key: string
  name: string
  description?: string
  project_type: ProjectType
  lead_id?: number
  task_names?: string[]
  /** The sub-workspace (client) and workspace (team) the project sits in. */
  client_id?: number | null
  primary_team_id?: number | null
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
      queryClient.invalidateQueries({ queryKey: ['reports', 'nav-tree'] })
    },
  })
}

export interface UpdateProjectPayload {
  /** Renaming re-keys every job (PG-12 -> Pochin-12); old keys keep working. */
  key?: string
  name?: string
  description?: string
  lead_id?: number
  client_id?: number | null
  primary_team_id?: number | null
  contributing_team_ids?: number[]
  budgeted_hours?: number | null
  deadline?: string | null
  special_notes?: string
  job_value?: string | null
  job_value_currency?: string
  task_names?: string[]
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

export function useCreateLabel(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; color?: string }) => {
      const { data } = await apiClient.post<Label>(`/projects/${key}/labels/`, payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects', key] }),
  })
}

export function useUpdateLabel(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...patch }: { id: number; name?: string; color?: string }) => {
      const { data } = await apiClient.patch<Label>(`/projects/${key}/labels/${id}/`, patch)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects', key] })
      queryClient.invalidateQueries({ queryKey: ['issues'] }) // cards show label names
    },
  })
}
