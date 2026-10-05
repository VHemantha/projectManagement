import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

export type RunStatus = 'running' | 'complete' | 'partial' | 'failed'
export type Verdict = 'ready' | 'ready_with_exceptions' | 'not_ready' | ''
export type Severity = 'high' | 'medium' | 'low'
export type FindingStatus = 'addressed' | 'exception' | 'missing' | 'unclear'
export type FindingKind = 'fact' | 'rule' | 'client_preference' | 'ai_suggestion'
export type Disposition = 'accepted' | 'rejected' | 'not_applicable' | 'needs_clarification'
export type TrailStage = 'read' | 'checked' | 'compared' | 'judged' | 'verified'

export interface Evidence {
  id: string
  file_name: string
  location: string
  quote: string
  drive_url: string
}

export interface Finding {
  id: number
  finding_id: string
  direction_ref: string
  area: string
  status: FindingStatus
  severity: Severity
  kind: FindingKind
  title: string
  why: string
  source: 'rule' | 'ai'
  confidence: Severity
  evidence: Evidence[]
  disposition: { disposition: Disposition; by: string; at: string } | null
}

export interface TrailStep {
  label: string
  detail: Record<string, unknown>[]
  [count: string]: unknown
}

export interface ProgressEvent {
  stage: TrailStage
  state: 'running' | 'done'
  label: string
  counts: Record<string, number> | null
}

/** A Direction Note item: typed by a person, or drafted by the AI with its reason. */
export interface DirectionItem {
  id: string
  text: string
  origin?: 'person' | 'ai'
  reason?: string
  basis?: 'history' | 'current' | 'standard' | ''
}

export interface RunSummary {
  run_id: string
  status: RunStatus
  verdict: Verdict
  summary: string
  coverage: { addressed: number; total: number }
  counts: Partial<Record<Severity, number>>
  created_at: string
  finished_at: string | null
  requested_by: string
  demo: boolean
}

export type YoyStatus = 'covered' | 'partly' | 'not_yet' | 'at_year_end' | 'not_expected' | 'unclear'

export interface YoyRef {
  id: string
  label: string
  evidence_id: string | null
}

export interface YoyLine {
  id: string
  label: string
  section: string
  last_year: number
  year_before: number | null
  this_year: number | null
  change: number | null
  change_pct: number | null
  status: YoyStatus
  comment: string
  question: string
  refs: YoyRef[]
  evidence_ids: string[]
}

/** This year's documents against last year's accounts. Every amount was produced by code. */
export interface YearOnYear {
  available: true
  how: 'model' | 'cache' | 'code only'
  this_year: string
  last_year: string
  period: string
  baseline: string[]
  documents: { this_year: number; last_year: number }
  summary: string[]
  lines: YoyLine[]
  checks: { label: string; passed: boolean; detail: string; evidence_ids: string[] }[]
  bank: { account: string; from: string; to: string; opening: number | null; closing: number | null; money_in: number; money_out: number; transactions: number }[]
  new_this_year: { text: string; refs: YoyRef[] }[]
  evidence?: Record<string, { file_name: string; location: string; quote: string; drive_url: string }>
}

export interface Run extends RunSummary {
  direction_items: (DirectionItem & { addressed: boolean })[]
  trail: Partial<Record<TrailStage, TrailStep>>
  progress: ProgressEvent[]
  skipped: { task_id: string; direction_ref: string; what: string; reason: string }[]
  failure_reason: string
  usage: {
    totals?: { input: number; output: number; cache_write: number; cache_read: number }
    model_calls?: number
    reader_calls?: number
    cost_usd?: number
    cache_share?: number
    reused_answers?: number
  }
  models: Partial<Record<'reader' | 'judge' | 'escalate', string>>
  duration_s: number | null
  findings: Finding[]
  /** Absent on runs from before the year-on-year analysis existed. */
  analysis?: YearOnYear | { available: false; reason: string }
}

export interface PrecheckSetup {
  drive_folder_url: string
  drive_folder_id: string
  direction_items: DirectionItem[]
  missing: ('drive_folder' | 'direction_note')[]
  /** True once the Drive folder is linked. With no Direction Note the AI drafts one first. */
  ready: boolean
}

export interface JobPrecheck {
  job: string
  setup: PrecheckSetup
  latest: Run | null
  history: RunSummary[]
  /** The latest "draft the Direction Note" request, if any. */
  draft: { status: RunStatus; failure_reason: string; created_at: string } | null
}

/** While a run is live the socket pushes changes; this slow poll is the fallback. */
const RUNNING_POLL_MS = 4000

export function useJobPrecheck(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey],
    queryFn: async () => (await apiClient.get<JobPrecheck>(`/precheck/jobs/${jobKey}/`)).data,
    refetchInterval: (query) =>
      query.state.data?.latest?.status === 'running' || query.state.data?.draft?.status === 'running' ? RUNNING_POLL_MS : false,
  })
}

export function usePrecheckRun(runId: string | null) {
  return useQuery({
    queryKey: ['precheck-run', runId],
    enabled: !!runId,
    queryFn: async () => (await apiClient.get<Run>(`/precheck/runs/${runId}/`)).data,
  })
}

export function useRunPrecheck(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => (await apiClient.post<Run>('/precheck/runs/', { job: jobKey })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] }),
  })
}

/** Ask the AI to draft Direction Note items (from the client's past jobs and the folder). */
export function useDraftDirections(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => (await apiClient.post(`/precheck/jobs/${jobKey}/draft/`)).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] }),
  })
}

export function useSavePrecheckSetup(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { drive_folder_url?: string; direction_items?: string[] }) =>
      (await apiClient.put<PrecheckSetup>(`/precheck/jobs/${jobKey}/setup/`, payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] }),
  })
}

/** A decision on a finding; `cleared` undoes it. */
export function useSetDisposition(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ findingId, disposition }: { findingId: number; disposition: Disposition | 'cleared' }) =>
      (await apiClient.post(`/precheck/findings/${findingId}/disposition/`, { disposition })).data,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] })
      queryClient.invalidateQueries({ queryKey: ['precheck-run'] })
    },
  })
}
