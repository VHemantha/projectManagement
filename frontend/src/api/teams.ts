import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Paginated, TeamDetail, TeamMembership, TeamSummary } from './types'

export function useTeams() {
  return useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<TeamSummary>>('/teams/')
      return data.results
    },
  })
}

export function useTeam(id: number | string | undefined) {
  return useQuery({
    queryKey: ['teams', id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await apiClient.get<TeamDetail>(`/teams/${id}/`)
      return data
    },
  })
}

export function useCreateTeam() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; description?: string }) => {
      const { data } = await apiClient.post<TeamDetail>('/teams/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['teams'] }),
  })
}

export function useAddTeamMember(teamId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { user_id: number; role: string }) => {
      const { data } = await apiClient.post<TeamMembership>(`/teams/${teamId}/members/`, payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['teams', teamId] }),
  })
}

export function useRemoveTeamMember(teamId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (membershipId: number) => {
      await apiClient.delete(`/teams/${teamId}/members/${membershipId}/`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['teams', teamId] }),
  })
}
