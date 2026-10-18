import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Run, SourceRef } from './precheck'

export interface GuideStep {
  area: string
  step: string
  check: string
  waits_on_client: boolean
  sources: SourceRef[]
  flags: string[]
}

export interface GuideOutput {
  summary: string
  steps: GuideStep[]
  decision: { state: string; label: string; reason: string }
  evidence: Record<string, { file_name: string; location: string; quote: string; drive_url: string }>
  how?: string
}

export interface GuideState {
  latest: (Run & { kind: string; guide: GuideOutput | Record<string, never> }) | null
  history: { run_id: string; status: string; created_at: string }[]
  has_precheck: boolean
}

export function useJobGuide(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'guide'],
    queryFn: async () => (await apiClient.get<GuideState>(`/precheck/jobs/${jobKey}/guide/`)).data,
    refetchInterval: (query) => (query.state.data?.latest?.status === 'running' ? 4000 : false),
  })
}

export function useRunGuide(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => (await apiClient.post(`/precheck/jobs/${jobKey}/guide/`, {})).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] }),
  })
}

export type MilestoneKind = 'precheck' | 'guide' | 'review' | 'checks' | 'preparation' | 'adjustments'

export interface Milestone {
  id: number
  kind: MilestoneKind
  label: string
  on: string
  note: string
  auto: boolean
  by: string
  created_at: string
}

/** When each stage of the task happened: the AI's postings, and the stages people stamp. */
export function useMilestones(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'milestones'],
    queryFn: async () => (await apiClient.get<{ milestones: Milestone[] }>(`/precheck/jobs/${jobKey}/milestones/`)).data,
  })
}

export function useStampMilestone(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { kind: 'checks' | 'preparation' | 'adjustments'; on?: string; note?: string }) =>
      (await apiClient.post<Milestone>(`/precheck/jobs/${jobKey}/milestones/`, body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'milestones'] }),
  })
}

export interface PersonKpi {
  person: { id: number; display_name: string }
  period: { from: string; to: string }
  finished: {
    tasks: number
    within_budget: number
    over_budget: number
    pct_within_budget: number | null
    budgeted_hours: number
    actual_hours: number
    efficiency_pct: number | null
  }
  open: { tasks: number; over_budget_already: number }
  tasks: {
    key: string
    summary: string
    project: string
    status: string
    done: boolean
    budgeted_hours: number
    actual_hours: number
    variance_hours: number
    within_budget: boolean
  }[]
}

/** A person's budget KPI: their assigned tasks with budgeted time, hours they logged, within budget or not. */
export function usePersonKpi(userId: number | undefined, from: string, to: string) {
  return useQuery({
    queryKey: ['kpi', userId, from, to],
    enabled: !!userId,
    queryFn: async () => (await apiClient.get<PersonKpi>(`/reports/people/${userId}/kpi/`, { params: { from, to } })).data,
  })
}
