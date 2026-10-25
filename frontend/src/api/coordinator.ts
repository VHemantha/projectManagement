import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

/** The AI project coordination agent: each person's conversation with it, and the CEO's controls. */

interface Person {
  id: number
  display_name: string
}

export interface CoordinatorMe {
  conversation_id: number
  is_ceo: boolean
  agent: Person
}

export interface CoordinatorSettings {
  paused: boolean
  shadow_mode: boolean
  timezone: string
  daily_cost_cap_usd: number
  updated_by: Person | null
  updated_at: string
}

export interface RuleInfo {
  key: string
  label: string
  default: number | string
  kind: 'number' | 'time' | 'choice'
  help: string
  minimum: number | null
  maximum: number | null
  choices: string[]
  current: number | string
}

export interface PolicyVersion {
  id: number
  key: string
  scope: 'company' | 'team' | 'client' | 'person' | 'job'
  scope_id: string
  value: number | string
  version: number
  active: boolean
  note: string
  effective_from: string
  expires_at: string | null
  approved_by: Person | null
  created_at: string
}

export interface AuditRow {
  id: number
  actor: Person | null
  action: string
  target: string
  allowed: boolean
  detail: Record<string, unknown>
  created_at: string
}

export interface AgentActionRow {
  id: number
  trigger: string
  target: Person | null
  issue: string
  reason: string
  shadow: boolean
  created_at: string
}

export interface CaseRow {
  id: number
  issue: string
  title: string
  person: Person
  kind: string
  kind_label: string
  state: 'asked' | 'answered' | 'escalated' | 'resolved'
  state_label: string
  due_date: string | null
  revised_due: string | null
  asked: number
  last_asked_at: string | null
  escalated_to: Person | null
  opened_at: string
  closed_reason: string
  commitment: { eta_date: string | null; remaining_hours: number | null; cause: string; status: string } | null
}

export type LeaveKind = 'annual' | 'sick' | 'training' | 'other'

export interface LeaveRow {
  id: number
  user: Person
  start_date: string
  end_date: string
  kind: LeaveKind
  kind_label: string
  hours_per_day: number | null
  note: string
  status: 'pending' | 'approved' | 'rejected'
  status_label: string
  decided_by: Person | null
  decided_at: string | null
  created_at: string
}

export interface ScheduleRow {
  user: Person
  hours: number[]
  note: string
}

const get = async <T,>(url: string) => (await apiClient.get<T>(url)).data

export function useCoordinatorMe(enabled = true) {
  return useQuery({ queryKey: ['coordinator', 'me'], enabled, queryFn: () => get<CoordinatorMe>('/coordinator/me/'), staleTime: 10 * 60 * 1000 })
}

export function useCoordinatorSettings() {
  return useQuery({ queryKey: ['coordinator', 'settings'], queryFn: () => get<CoordinatorSettings>('/coordinator/settings/') })
}

export function useUpdateCoordinatorSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (patch: Partial<Pick<CoordinatorSettings, 'paused' | 'shadow_mode' | 'timezone' | 'daily_cost_cap_usd'>>) =>
      (await apiClient.patch<CoordinatorSettings>('/coordinator/settings/', patch)).data,
    onSuccess: (data) => {
      qc.setQueryData(['coordinator', 'settings'], data)
      qc.invalidateQueries({ queryKey: ['coordinator', 'audit'] })
    },
  })
}

export function usePolicies() {
  return useQuery({ queryKey: ['coordinator', 'policies'], queryFn: () => get<{ rules: RuleInfo[]; policies: PolicyVersion[] }>('/coordinator/policies/') })
}

export function useSetPolicy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { key: string; value: number | string; scope?: string; scope_id?: string; note?: string; expires_at?: string }) =>
      (await apiClient.post<PolicyVersion>('/coordinator/policies/', body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['coordinator', 'policies'] })
      qc.invalidateQueries({ queryKey: ['coordinator', 'audit'] })
    },
  })
}

export function useAudit() {
  return useQuery({ queryKey: ['coordinator', 'audit'], queryFn: () => get<{ entries: AuditRow[] }>('/coordinator/audit/') })
}

export function useCases() {
  return useQuery({ queryKey: ['coordinator', 'cases'], queryFn: () => get<{ cases: CaseRow[] }>('/coordinator/cases/') })
}

export function useAgentActions() {
  return useQuery({ queryKey: ['coordinator', 'actions'], queryFn: () => get<{ actions: AgentActionRow[] }>('/coordinator/actions/') })
}

export function useLeave(status?: LeaveRow['status']) {
  return useQuery({
    queryKey: ['coordinator', 'leave', status ?? 'all'],
    queryFn: () => get<{ leave: LeaveRow[] }>(`/coordinator/leave/${status ? `?status=${status}` : ''}`),
  })
}

export function useRequestLeave() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { start_date: string; end_date: string; kind: LeaveKind; hours_per_day?: number | null; note?: string }) =>
      (await apiClient.post<LeaveRow>('/coordinator/leave/', body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coordinator', 'leave'] }),
  })
}

export function useDecideLeave() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, status }: { id: number; status: 'approved' | 'rejected' }) =>
      (await apiClient.post<LeaveRow>(`/coordinator/leave/${id}/decide/`, { status })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['coordinator', 'leave'] })
      qc.invalidateQueries({ queryKey: ['coordinator', 'audit'] })
    },
  })
}

export function useWithdrawLeave() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => apiClient.delete(`/coordinator/leave/${id}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coordinator', 'leave'] }),
  })
}

export function useHolidays() {
  return useQuery({ queryKey: ['coordinator', 'holidays'], queryFn: () => get<{ holidays: { date: string; name: string }[] }>('/coordinator/holidays/') })
}

export function useAddHoliday() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { date: string; name: string }) => (await apiClient.post('/coordinator/holidays/', body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coordinator', 'holidays'] }),
  })
}

export function useRemoveHoliday() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (date: string) => apiClient.delete(`/coordinator/holidays/?date=${date}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coordinator', 'holidays'] }),
  })
}

export function useSchedules() {
  return useQuery({ queryKey: ['coordinator', 'schedules'], queryFn: () => get<{ schedules: ScheduleRow[] }>('/coordinator/schedules/') })
}

export function useSetSchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ userId, hours, note }: { userId: number; hours: number[]; note: string }) =>
      (await apiClient.put(`/coordinator/schedules/${userId}/`, { hours, note })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coordinator', 'schedules'] }),
  })
}
