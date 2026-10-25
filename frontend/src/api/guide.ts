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

type Evidence = Record<string, { file_name: string; location: string; quote: string; drive_url: string }>

/** A guide written before 21 Oct 2026: a flat list of steps. Still shown as it was. */
export interface GuideOutput {
  summary: string
  steps: GuideStep[]
  decision: { state: string; label: string; reason: string }
  evidence: Evidence
  how?: string
}

/** Every item: the ids of the events (E1, E2, ...) it follows through, its sources, code's flags. */
interface GuideItem {
  events?: string[]
  sources?: SourceRef[]
  flags: string[]
}

export interface GuideEvent extends GuideItem {
  id: string
  event: string
  status: 'confirmed' | 'suspected'
  why_it_matters: string
  action: string
  effect: string
  /** Where it is not yet followed through: "sequence", "checklist", "query". */
  not_followed_through: string[]
}

/** The eight-section preparation guide (AFIT's agreed structure, 21 Oct 2026). */
export interface GuideV2 {
  format: 2
  summary: string
  decision: { state: string; label: string; reason: string }
  snapshot: GuideItem & { activities: string; assets_and_funding: string; records: string; bookkeeping: string; period: string }
  events: GuideEvent[]
  prior_year: (GuideItem & { item: string; kind: 'error' | 'reviewer_point' | 'unresolved' | 'policy' | 'balance'; follow_through: string })[]
  risks: (GuideItem & { area: string; what_could_be_wrong: string; examine: string; evidence: string })[]
  sequence: (GuideItem & { step: string; depends_on: string; can_start_now: boolean; escalate: string })[]
  judgments: (GuideItem & { judgment: string; evidence: string; manager_approval: boolean; reference: string })[]
  queries: {
    manager: (GuideItem & { question: string })[]
    client: (GuideItem & { question: string })[]
    outstanding: (GuideItem & { item: string })[]
  }
  checklist: (GuideItem & { check: string; status: 'done' | 'open' | 'na' })[]
  /** This year's findings for next year's preparer (absent on guides before 24 Oct 2026). */
  roll_forward?: (GuideItem & { item: string; why: string })[]
  words: number
  flags: string[]
  evidence: Evidence
  how?: string
}

export interface GuideState {
  latest: (Run & { kind: string; guide: GuideOutput | GuideV2 | Record<string, never> }) | null
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
