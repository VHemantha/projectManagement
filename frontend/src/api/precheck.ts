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

/** A place a reason rests on: a questionnaire line, last year's line, a file… with its link. */
export interface SourceRef {
  id: string
  label: string
  evidence_id: string | null
}

export interface PrecheckItem {
  group: string
  item: string
  decision: 'request' | 'already_provided' | 'not_needed'
  reason: string
  sources: SourceRef[]
  documents: SourceRef[]
  /** Raised by code: no_source, no_file_named, figure_not_in_documents. */
  flags: string[]
}

/** The pre-check: decision, key documents, business nature, every item with its reason, and
 * the email to the client (drafted, never sent). */
export interface PrecheckOutput {
  decision: { state: 'blocked' | 'requests' | 'nothing'; label: string; reason: string }
  key_documents: { role: string; label: string; found: boolean; note: string; files: { name: string; evidence_id: string | null }[] }[]
  business_nature: {
    type: string
    label: string
    summary: string
    reasoning: string
    fixed: boolean
    sources: SourceRef[]
    facts: { text: string; sources: SourceRef[] }[]
  } | null
  requests: PrecheckItem[]
  provided: PrecheckItem[]
  not_needed: PrecheckItem[]
  preparer_notes: { text: string; sources: SourceRef[] }[]
  lessons_applied: { id: string; text: string }[]
  email: { subject: string; body: string }
  evidence: Record<string, { file_name: string; location: string; quote: string; drive_url: string }>
  how?: string
}

export type LessonKind = 'not_needed' | 'wrong_reason' | 'missed' | 'other'

export interface Lesson {
  id: number
  scope: 'client' | 'firm'
  status: 'active' | 'pending' | 'disabled'
  kind: LessonKind
  precheck_type: string
  item: string
  note: string
  created_by: string
  created_at: string
  task: string
}

export interface Run extends RunSummary {
  direction_items: (DirectionItem & { addressed: boolean })[]
  /** The business nature the pre-check worked to. */
  precheck_type?: string
  /** The decision in words: Blocked, Requests to send, Nothing to request. */
  readiness?: string
  /** Absent on runs from before the request-list pre-check (5 Oct 2026). */
  precheck?: PrecheckOutput
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
  models: Partial<Record<string, string>>
  duration_s: number | null
  /** Findings of runs from before 5 Oct 2026; new runs list requests in `precheck` instead. */
  findings: Finding[]
}

export type PrecheckType = 'auto' | 'residential_rental' | 'general' | 'investment'

/** Where a person says each key document is: a path inside the task folder or a Drive link,
 * several separated by ";". Empty: the pre-check searches the folder. */
export interface KeyPaths {
  questionnaire: string
  last_year_fs: string
  last_year_workpapers: string
}

export interface PrecheckSetup {
  drive_folder_url: string
  drive_folder_id: string
  /** Which kind of pre-check: a type other than general adds the firm's standard checklist. */
  precheck_type: PrecheckType
  precheck_types: { value: PrecheckType; label: string }[]
  key_paths?: KeyPaths
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
    mutationFn: async (payload: {
      drive_folder_url?: string
      direction_items?: string[]
      precheck_type?: PrecheckType
      key_paths?: KeyPaths
    }) =>
      (await apiClient.put<PrecheckSetup>(`/precheck/jobs/${jobKey}/setup/`, payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] }),
  })
}

/** Lessons this task's pre-check applies, and (for a lead or admin) firm-wide ones to approve. */
export function useLessons(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'lessons'],
    queryFn: async () =>
      (await apiClient.get<{ lessons: Lesson[]; pending_firm_wide: Lesson[]; can_approve: boolean }>(`/precheck/jobs/${jobKey}/lessons/`)).data,
  })
}

/** Teach the pre-check from a correction. */
export function useTeachLesson(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { kind: LessonKind; item: string; note: string; firm_wide: boolean }) =>
      (await apiClient.post<Lesson>(`/precheck/jobs/${jobKey}/lessons/`, payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'lessons'] }),
  })
}

/** Approve a firm-wide lesson, or switch one off. */
export function useSetLessonStatus(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, status }: { id: number; status: 'active' | 'disabled' }) =>
      (await apiClient.patch<Lesson>(`/precheck/lessons/${id}/`, { status })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'lessons'] }),
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
