import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { BurndownData, Paginated, Sprint, VelocityRow } from './types'

export function useSprints(projectKey: string | undefined) {
  return useQuery({
    queryKey: ['sprints', projectKey],
    enabled: !!projectKey,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<Sprint>>(`/projects/${projectKey}/sprints/`)
      return data.results
    },
  })
}

export function useCreateSprint(projectKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; goal?: string }) => {
      const { data } = await apiClient.post<Sprint>(`/projects/${projectKey}/sprints/`, payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sprints', projectKey] }),
  })
}

export function useStartSprint(projectKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      ...payload
    }: {
      id: number
      start_date: string
      end_date: string
      goal?: string
    }) => {
      const { data } = await apiClient.post<Sprint>(`/sprints/${id}/start/`, payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sprints', projectKey] }),
  })
}

export function useSprintBurndown(sprintId: number | undefined) {
  return useQuery({
    queryKey: ['sprints', sprintId, 'burndown'],
    enabled: !!sprintId,
    queryFn: async () => {
      const { data } = await apiClient.get<BurndownData>(`/sprints/${sprintId}/burndown/`)
      return data
    },
  })
}

export function useVelocity(projectKey: string | undefined) {
  return useQuery({
    queryKey: ['projects', projectKey, 'velocity'],
    enabled: !!projectKey,
    queryFn: async () => {
      const { data } = await apiClient.get<VelocityRow[]>(`/projects/${projectKey}/velocity/`)
      return data
    },
  })
}

export function useCompleteSprint(projectKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, moveTo }: { id: number; moveTo: 'backlog' | number }) => {
      const { data } = await apiClient.post<Sprint>(`/sprints/${id}/complete/`, { move_to: String(moveTo) })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sprints', projectKey] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
  })
}
