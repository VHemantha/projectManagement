import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Paginated, TimeEntry, Timesheet, User } from './types'
import { useAuthStore } from '@/store/authStore'

const RUNNING_TIMER_KEY = ['time-entries', 'running']

export function useRunningTimer() {
  const accessToken = useAuthStore((s) => s.accessToken)
  return useQuery({
    queryKey: RUNNING_TIMER_KEY,
    enabled: !!accessToken,
    queryFn: async () => {
      const { data } = await apiClient.get<TimeEntry | null>('/time-entries/running/')
      return data
    },
    refetchInterval: 30_000,
  })
}

export function useStartTimer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (issueId?: number) => {
      const { data } = await apiClient.post<TimeEntry>('/time-entries/start/', {
        issue_id: issueId ?? null,
      })
      return data
    },
    onSuccess: (entry) => {
      queryClient.setQueryData(RUNNING_TIMER_KEY, entry)
      queryClient.invalidateQueries({ queryKey: ['time-entries'] })
    },
  })
}

export function useStopTimer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (entryId: number) => {
      const { data } = await apiClient.post<TimeEntry>(`/time-entries/${entryId}/stop/`)
      return data
    },
    onSuccess: () => {
      queryClient.setQueryData(RUNNING_TIMER_KEY, null)
      queryClient.invalidateQueries({ queryKey: ['time-entries'] })
    },
  })
}

export interface TimeEntryQueryParams {
  user?: number
  user_in?: string
  project?: string
  issue?: number
  billable?: boolean
  date_from?: string
  date_to?: string
  page_size?: number
}

export function useTimeEntries(params: TimeEntryQueryParams, enabled = true) {
  return useQuery({
    queryKey: ['time-entries', params],
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<TimeEntry>>('/time-entries/', { params })
      return data.results
    },
  })
}

export interface ManualTimeEntryPayload {
  /** Someone else's id, to log the time on their behalf (a lead, for a person they lead). */
  user_id?: number
  issue_id?: number | null
  description?: string
  work_date: string
  hours: number
  is_billable?: boolean
}

export function useCreateTimeEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ManualTimeEntryPayload) => {
      const { hours, ...rest } = payload
      const { data } = await apiClient.post<TimeEntry>('/time-entries/', {
        ...rest,
        duration_seconds_input: Math.round(hours * 3600),
      })
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['time-entries'] }),
  })
}

export function useUpdateTimeEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, hours, ...rest }: { id: number; hours?: number } & Partial<ManualTimeEntryPayload>) => {
      const payload: Record<string, unknown> = { ...rest }
      if (hours != null) payload.duration_seconds_input = Math.round(hours * 3600)
      const { data } = await apiClient.patch<TimeEntry>(`/time-entries/${id}/`, payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['time-entries'] }),
  })
}

export function useDeleteTimeEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/time-entries/${id}/`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['time-entries'] }),
  })
}

/** The people this user may log time for: those they lead (everyone, for an admin). */
export function useOnBehalfPeople(enabled = true) {
  return useQuery({
    queryKey: ['time-entries', 'on-behalf-people'],
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<User[]>('/time-entries/on-behalf-people/')
      return data
    },
  })
}

export function useTimesheets(inbox = false) {
  return useQuery({
    queryKey: ['timesheets', { inbox }],
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<Timesheet>>('/timesheets/', {
        params: inbox ? { inbox: 'true' } : undefined,
      })
      return data.results
    },
  })
}

export function useGetOrCreateTimesheet() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { period_start: string; period_end: string }) => {
      const { data } = await apiClient.post<Timesheet>('/timesheets/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['timesheets'] }),
  })
}

export function useSubmitTimesheet() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await apiClient.post<Timesheet>(`/timesheets/${id}/submit/`)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timesheets'] })
      queryClient.invalidateQueries({ queryKey: ['time-entries'] })
    },
  })
}

export function useApproveTimesheet() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await apiClient.post<Timesheet>(`/timesheets/${id}/approve/`)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['timesheets'] }),
  })
}

export function useRejectTimesheet() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, note }: { id: number; note: string }) => {
      const { data } = await apiClient.post<Timesheet>(`/timesheets/${id}/reject/`, { note })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timesheets'] })
      queryClient.invalidateQueries({ queryKey: ['time-entries'] })
    },
  })
}

// --- time not on a job, and the efficiency tracker (AFIT, 21 Nov 2026) -------------------------------------

export interface ActivityTask {
  id: number
  key: string
  activity: 'idle' | 'administration' | 'training'
  label: string
}

/** The hidden cards for time not on a job: Idle, Administration, Training (never on a Kanban view). */
export function useActivityTasks(enabled = true) {
  return useQuery({
    queryKey: ['timesheets', 'activities'],
    enabled,
    staleTime: 60 * 60 * 1000,
    queryFn: async () => (await apiClient.get<ActivityTask[]>('/timesheets/activities/')).data,
  })
}

export interface EfficiencyDay {
  date: string
  expected: number
  logged: number
  jobs: number
  idle: number
  administration: number
  training: number
  under: boolean
}

export interface EfficiencySummary {
  expected: number
  logged: number
  jobs: number
  non_job: number
  efficiency_pct: number | null
  on_jobs_pct: number | null
  days_under: number
  working_days: number
}

export interface EfficiencyTracker {
  user: { id: number; name: string }
  target: number
  days: EfficiencyDay[]
  summary: EfficiencySummary
  jobs: { key: string; summary: string; budget: number | null; logged: number; used_pct: number | null }[]
}

export interface TeamEfficiency {
  target: number
  days: number
  people: { user: { id: number; name: string }; summary: EfficiencySummary; last_day: EfficiencyDay | null }[]
}

export function useEfficiency(days = 10, userId?: number) {
  return useQuery({
    queryKey: ['timesheets', 'efficiency', days, userId ?? 'me'],
    queryFn: async () => (await apiClient.get<EfficiencyTracker>('/timesheets/efficiency/', { params: { days, ...(userId ? { user: userId } : {}) } })).data,
  })
}

export function useTeamEfficiency(days = 10, enabled = true) {
  return useQuery({
    queryKey: ['timesheets', 'efficiency', 'team', days],
    enabled,
    queryFn: async () => (await apiClient.get<TeamEfficiency>('/timesheets/efficiency/', { params: { days, team: 1 } })).data,
  })
}
