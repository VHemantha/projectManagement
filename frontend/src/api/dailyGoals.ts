import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { IssueMini, User } from './types'

export type DailyGoalStatus = 'planned' | 'in_progress' | 'achieved' | 'not_achieved' | 'carried_over'

export type LeadCheck = '' | 'confirmed' | 'not_done'

export interface DailyGoal {
  id: number
  user: User
  date: string
  text: string
  linked_issue: IssueMini | null
  /** The linked task's sub-workspace ("ABC Ltd"). */
  sub_workspace: string | null
  /** Hours set aside for it on the day. */
  planned_hours: number | null
  /** The day the job is to be finished. */
  complete_by: string | null
  /** When the linked task was finished (its own record), else null. */
  task_done: string | null
  status: DailyGoalStatus
  note: string
  order: number
  carried_over_from: number | null
  /** The team lead's check of the result. */
  lead_check: LeadCheck
  checked_by: User | null
  checked_at: string | null
  created_at: string
  updated_at: string
}

export interface NewPlanItem {
  date: string
  text?: string
  linked_issue_id?: number | null
  planned_hours?: number | null
  complete_by?: string | null
}

export interface TeamPlanRow {
  person: User
  goals: DailyGoal[]
  planned_hours: number
  logged_hours: number
  achieved: number
  not_achieved: number
  unchecked: number
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
    mutationFn: async (payload: NewPlanItem) => {
      const { data } = await apiClient.post<DailyGoal>('/daily-goals/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['daily-goals'] }),
  })
}

export function useUpdateDailyGoal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      ...patch
    }: {
      id: number
      status?: DailyGoalStatus
      note?: string
      order?: number
      text?: string
      planned_hours?: number | null
      complete_by?: string | null
    }) => {
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

/** The morning plans of everyone the user leads (everyone, for an admin or the CEO) on a day. */
export function useTeamPlans(date: string) {
  return useQuery({
    queryKey: ['daily-goals', 'team', date],
    queryFn: async () => {
      const { data } = await apiClient.get<{ date: string; people: TeamPlanRow[] }>('/daily-goals/team/', { params: { date } })
      return data
    },
  })
}

/** A team lead's check of a plan item's result. */
export function useCheckGoal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, result }: { id: number; result: LeadCheck }) => {
      const { data } = await apiClient.post<DailyGoal>(`/daily-goals/${id}/check/`, { result })
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
