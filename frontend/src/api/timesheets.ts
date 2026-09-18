import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Paginated, TimeEntry, Timesheet } from './types'
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

export async function downloadTimeReportCsv(params: TimeEntryQueryParams) {
  const { data } = await apiClient.get('/time-reports/export/', { params, responseType: 'blob' })
  const url = URL.createObjectURL(data as Blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'time-report.csv'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
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
