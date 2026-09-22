import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { IssueMini, User } from './types'

export type DailyGoalStatus = 'planned' | 'in_progress' | 'achieved' | 'not_achieved' | 'carried_over'

export interface DailyGoal {
  id: number
  user: User
  date: string
  text: string
  linked_issue: IssueMini | null
  status: DailyGoalStatus
  note: string
  order: number
  carried_over_from: number | null
  created_at: string
  updated_at: string
}

export function useDailyGoals(date: string, userId?: number) {
  return useQuery({
    queryKey: ['daily-goals', userId ?? 'me', date],
    queryFn: async () => {
      const { data } = await apiClient.get<DailyGoal[]>('/daily-goals/', {
        params: { date, ...(userId ? { user: userId } : {}) },
      })
      return data
    },
  })
}

export function useDailyGoalsRange(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ['daily-goals', 'me', 'range', dateFrom, dateTo],
    queryFn: async () => {
      const { data } = await apiClient.get<DailyGoal[]>('/daily-goals/', {
        params: { date_from: dateFrom, date_to: dateTo },
      })
      return data
    },
  })
}

export function useCreateDailyGoal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { date: string; text: string; linked_issue_id?: number | null }) => {
      const { data } = await apiClient.post<DailyGoal>('/daily-goals/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['daily-goals'] }),
  })
}

export function useUpdateDailyGoal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...patch }: { id: number; status?: DailyGoalStatus; note?: string; order?: number; text?: string }) => {
      const { data } = await apiClient.patch<DailyGoal>(`/daily-goals/${id}/`, patch)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['daily-goals'] }),
  })
}

export function useCarryOverGoal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await apiClient.post<DailyGoal>(`/daily-goals/${id}/carry-over/`)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['daily-goals'] }),
  })
}

export function useTeamDailyGoals(teamId: number | undefined, date?: string) {
  return useQuery({
    queryKey: ['teams', teamId, 'daily-goals', date ?? 'all'],
    enabled: !!teamId,
    queryFn: async () => {
      const { data } = await apiClient.get<DailyGoal[]>(`/teams/${teamId}/daily-goals/`, {
        params: date ? { date } : undefined,
      })
      return data
    },
  })
}

export function useTeamDailyGoalsRange(teamId: number | undefined, dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ['teams', teamId, 'daily-goals', 'range', dateFrom, dateTo],
    enabled: !!teamId,
    queryFn: async () => {
      const { data } = await apiClient.get<DailyGoal[]>(`/teams/${teamId}/daily-goals/`, {
        params: { date_from: dateFrom, date_to: dateTo },
      })
      return data
    },
  })
}
