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
  decision: 'request' | 'already_provided' | 'not_needed' | 'ask_accountant'
  /** "blocking": the gap stops preparation (asked first). */
  priority?: 'blocking' | 'normal'
  reason: string
  sources: SourceRef[]
  documents: SourceRef[]
  /** Raised by code: no_source, no_file_named, figure_not_in_documents. */
  flags: string[]
  /** The item's missing-information gap: the AI keeps checking every document for it (12 Nov 2026). */
  gap?: { gap_id: string; status: GapStatus; still_needed: string }
  /** What the policy check did to the point (20 Nov 2026): checked against these policies, and kept,
   * changed (with what it was before) or added because a policy requires it. */
  policy?: PointPolicy
}

export interface PolicyRef {
  id: number
  title: string
  scope_label: string
}

export interface PointPolicy {
  changed: boolean
  added?: boolean
  policies: PolicyRef[]
  note?: string
  was?: { decision: PrecheckItem['decision']; label: string; priority: string; reason: string }
}

/** The run's check of every point against the firm's pre-check policies (20 Nov 2026). */
export interface PolicyCheck {
  checked: number
  changed: number
  added: number
  error?: string
  policies: { id: number; title: string; text: string; scope: PolicyScope; scope_label: string; applied_to: number }[]
}

/** A "not found" is provisional: OPEN until found (RESOLVED, or partly), or until the task's folder
 * has settled and the AI confirms it missing. CONFLICTING: documents give different values. */
export type GapStatus = 'OPEN' | 'PARTIALLY_RESOLVED' | 'RESOLVED' | 'CONFLICTING' | 'CONFIRMED_MISSING'

export interface JobGaps {
  provisional: boolean
  finalized_at: string | null
  updated_at: string | null
  counts: Partial<Record<GapStatus, number>>
  gaps: {
    gap_id: string
    group: string
    item: string
    status: GapStatus
    label: string
    still_needed: string
    origin: string
    evidence: { doc_name: string; location: string; quoted_snippet: string; extracted_value: string; drive_url: string; found_direction: string }[]
  }[]
}

/** The pre-check: decision, key documents, business nature, every item with its reason, and
 * the email to the client (drafted, never sent). */
/** The Job Snapshot (AFIT design requirements, 16 Nov 2026): the story of the client and its year,
 * shown before the findings. Every figure is worked out by code and opens to its source line. */
export type SnapshotStatus = 'confirmed' | 'inferred' | 'unresolved'

export interface SnapshotLine {
  label: string
  amount: number
  comparative: number | null
  source: SourceRef
}

export interface SnapshotGroup {
  label: string
  amount: number
  comparative: number | null
  derived?: boolean
  lines: SnapshotLine[]
}

export interface SnapshotKpi {
  label: string
  amount: number
  comparative: number | null
  change_pct: number | null
}

export interface SnapshotFigures {
  available: boolean
  basis: '' | 'trial_balance' | 'financial_statements'
  year_label: string
  comparative_label: string
  kpis?: SnapshotKpi[]
  income?: SnapshotLine[]
  expenses?: SnapshotLine[]
  asset_mix?: SnapshotGroup[]
  funding_mix?: SnapshotGroup[]
  current_accounts?: (SnapshotLine & { direction: string })[]
  this_year?: { revenue: number; expenses: number; net_profit: number; accounts_matched: number } | null
}

export interface JobSnapshot {
  figures: SnapshotFigures
  written: boolean
  changes: string[]
  business_story?: string
  story_flags?: string[]
  revenue_sources?: { label: string; detail: string; sources: SourceRef[] }[]
  financial_story?: string
  financial_flags?: string[]
  events?: { text: string; kind: string; status: SnapshotStatus; sources: SourceRef[]; flags: string[] }[]
  ownership?: { shareholders: { name: string; percent: number | null; sources: SourceRef[] }[]; note: string; sources: SourceRef[] }
  current_accounts?: string
  focus_areas?: { area: string; why: string; sources: SourceRef[] }[]
  understood?: { text: string; status: SnapshotStatus; sources: SourceRef[] }[]
  /** The findings under the firm's eleven headings, in order (21 Nov 2026); older runs have none. */
  sections?: SnapshotSection[]
  /** Company background facts from the task card (21 Nov 2026). */
  background?: { label: string; value: string }[]
}

export type SnapshotSectionKey =
  | 'company_background'
  | 'nature_of_business'
  | 'business_environment'
  | 'management_governance'
  | 'financial_performance'
  | 'financial_position'
  | 'significant_events'
  | 'accounting_policies'
  | 'key_risks'
  | 'prior_year_matters'
  | 'going_concern'

export interface SnapshotFinding {
  label: string
  text: string
  status: SnapshotStatus
  /** Key accounting risks only: how significant the risk of misstatement is. */
  level: 'high' | 'medium' | 'low' | 'none'
  sources: SourceRef[]
  flags: string[]
}

export interface SnapshotSection {
  key: SnapshotSectionKey
  title: string
  summary: string
  findings: SnapshotFinding[]
}

export interface PrecheckOutput {
  /** Runs from 16 Nov 2026 have one; it is shown first. */
  snapshot?: JobSnapshot
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
  /** Section B: questions for the accountant (never in the client email). Runs before 16 Oct 2026 have none. */
  accountant_questions?: PrecheckItem[]
  lessons_applied: { id: string; text: string }[]
  /** The staff's special notes the pre-check was given (13 Nov 2026); older runs have none. */
  special_notes?: NoteConsidered[]
  email: { subject: string; body: string }
  evidence: Record<string, { file_name: string; location: string; quote: string; drive_url: string }>
  how?: string
  /** Runs from 20 Nov 2026 with a policy that applies. */
  policy_check?: PolicyCheck
}

export type LessonKind = 'not_needed' | 'wrong_reason' | 'missed' | 'other'

export type LessonScope = 'client' | 'project' | 'team' | 'firm'

export interface Lesson {
  id: number
  scope: LessonScope
  scope_label?: string
  status: 'active' | 'pending' | 'disabled'
  kind: LessonKind
  /** Where the correction came from ("library": the AI rules page, not a task). */
  source?: 'precheck' | 'review' | 'ask' | 'library'
  /** The rule the AI drafted from the correction (null until drafted). */
  rule?: { title: string; when: string; do: string; why: string } | null
  drafting?: '' | 'drafting' | 'drafted' | 'failed'
  /** The type of check it is for ("" every type), and an entity type ("" any). */
  precheck_type: string
  precheck_type_label?: string
  entity_type?: string
  entity_label?: string
  item: string
  note: string
  created_by: string
  created_at: string
  task: string
}

/** What a lesson or rule is for: a type of check and, optionally, an entity type. */
export interface RuleTargets {
  precheck_type?: string
  entity_type?: string
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
  /** This year's draft financial statements, for the review. */
  draft_fs?: string
  /** This year's general ledger: an optional pre-check input. */
  general_ledger?: string
}

export type YesNoUnknown = 'yes' | 'no' | ''

export type EntityType = '' | 'trust' | 'close_company' | 'ltc' | 'sole_trader' | 'partnership' | 'body_corporate'

export interface AccountantSettings {
  /** Who the client is (AFIT, 27 Oct 2026); empty when not set. */
  entity_type?: EntityType
  /** Optional: the year end is enough. */
  year_start: string
  year_end: string
  xero_complete: YesNoUnknown
  ird_access: YesNoUnknown
  related_records: YesNoUnknown
  /** Where the client is (20 Nov 2026), for the pre-check policies set for a location. */
  location?: string
}

export interface AccountantAnswer {
  id: number
  question: string
  answer: string
  answered_by: string
  answered_at: string
}

/** The accountant's answers to the pre-check's questions; every later run is given them. */
export function useAccountantAnswers(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'answers'],
    queryFn: async () => (await apiClient.get<{ answers: AccountantAnswer[] }>(`/precheck/jobs/${jobKey}/answers/`)).data,
  })
}

export function useAnswerQuestion(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { question: string; answer: string }) =>
      (await apiClient.post<AccountantAnswer>(`/precheck/jobs/${jobKey}/answers/`, body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'answers'] }),
  })
}

/** Which AI agents a special note is for; none = every agent (AFIT, 13 Nov 2026). */
export type NoteAgent = 'precheck' | 'guide' | 'review' | 'ask'

/** A special note from staff to the AI agents on a task: they follow it when deciding and writing. */
export interface AgentNote {
  id: number
  text: string
  agents: NoteAgent[]
  by: string
  by_id: number | null
  created_at: string
  can_edit: boolean
}

/** On a result: each special note the agent was given, and whether it cited it. */
export interface NoteConsidered {
  id: string
  text: string
  by: string
  cited: boolean
}

export function useAgentNotes(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'notes'],
    queryFn: async () => (await apiClient.get<{ notes: AgentNote[]; max: number }>(`/precheck/jobs/${jobKey}/notes/`)).data,
  })
}

export function useAddAgentNote(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { text: string; agents: NoteAgent[] }) =>
      (await apiClient.post<AgentNote>(`/precheck/jobs/${jobKey}/notes/`, body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'notes'] }),
  })
}

export function useRemoveAgentNote(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/precheck/jobs/${jobKey}/notes/${id}/`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'notes'] }),
  })
}

export interface PrecheckSetup {
  drive_folder_url: string
  drive_folder_id: string
  /** Which kind of pre-check: a type other than general adds the firm's standard checklist. */
  precheck_type: PrecheckType
  precheck_types: { value: PrecheckType; label: string }[]
  entity_types?: { value: EntityType; label: string }[]
  key_paths?: KeyPaths
  /** Settings the accountant confirmed (general business and investment). */
  settings?: AccountantSettings
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
  draft: { run_id?: string; status: RunStatus; failure_reason: string; created_at: string } | null
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

/** The task's gaps, kept up to date by the AI's own re-checks (under ['precheck', key]: refreshed live). */
export function useJobGaps(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'gaps'],
    queryFn: async () => (await apiClient.get<JobGaps>(`/precheck/jobs/${jobKey}/gaps/`)).data,
  })
}

/** Check the task's gaps again now, or finalise the case (what is still not found is confirmed missing). */
export function useGapAction(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (action: 'recheck' | 'finalize') => (await apiClient.post(`/precheck/jobs/${jobKey}/gaps/`, { action })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] }),
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

/** Stop a running pre-check, guide, review or Direction Note draft. Every panel of the task is
 * refreshed, since any of them may have been showing it. */
export function useStopRun(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (runId: string) => (await apiClient.post<Run>(`/precheck/runs/${runId}/stop/`)).data,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['precheck', jobKey] })
      queryClient.invalidateQueries({ queryKey: ['precheck-run'] })
    },
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
      settings?: AccountantSettings
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
    mutationFn: async (payload: { kind: LessonKind; item: string; note: string; firm_wide: boolean } & RuleTargets) =>
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

export interface RuleLibrary {
  lessons: Lesson[]
  can_approve: boolean
  precheck_types: { value: string; label: string }[]
  entity_types: { value: string; label: string }[]
}

/** The AI rules: every lesson that applies beyond one client (leads and admins: all of them). */
export function useRuleLibrary(filters: { q?: string; type?: string; status?: string }) {
  return useQuery({
    queryKey: ['precheck', 'rules', filters],
    queryFn: async () => (await apiClient.get<RuleLibrary>('/precheck/lessons/', { params: filters })).data,
  })
}

/** A rule for a type of check, not from any task: active from a lead or admin, else waiting for one. */
export function useAddRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { kind: LessonKind; item: string; note: string } & RuleTargets) =>
      (await apiClient.post<Lesson>('/precheck/lessons/', payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck'] }),
  })
}

/** Approve a rule, or switch one off, from the AI rules page. */
export function useSetRuleStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, status }: { id: number; status: 'active' | 'disabled' }) =>
      (await apiClient.patch<Lesson>(`/precheck/lessons/${id}/`, { status })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck'] }),
  })
}

// --- pre-check policies (AFIT, 20 Nov 2026) ------------------------------------------------------

export type PolicyScope = 'client' | 'group' | 'location' | 'all'

export interface PolicyFeedback {
  id: number
  text: string
  context: string
  status: 'revising' | 'revised' | 'failed'
  summary: string
  task: string
  by: string
  created_at: string
}

export interface PrecheckPolicy {
  id: number
  scope: PolicyScope
  scope_label: string
  client: { id: number; name: string } | null
  group: string
  location: string
  precheck_type: string
  precheck_type_label: string
  title: string
  text: string
  active: boolean
  version: number
  history: { version: number; title: string; text: string; changed_by: string; changed_at: string; why: string }[]
  created_by: string
  updated_by: string
  updated_at: string
  can_change: boolean
  feedback?: PolicyFeedback[]
}

export interface PolicyLibrary {
  policies: PrecheckPolicy[]
  scopes: { value: PolicyScope; label: string }[]
  clients: { id: number; name: string }[]
  groups: string[]
  locations: string[]
  precheck_types: { value: string; label: string }[]
}

export interface PolicyInput {
  scope: PolicyScope
  client_id?: number | null
  group?: string
  location?: string
  precheck_type?: string
  title: string
  text: string
  active?: boolean
}

/** The firm's pre-check policies; with `task`, those that apply to that task. */
export function usePolicies(filters: { task?: string; q?: string; scope?: string } = {}) {
  return useQuery({
    queryKey: ['precheck', 'policies', filters],
    queryFn: async () => (await apiClient.get<PolicyLibrary>('/precheck/policies/', { params: filters })).data,
  })
}

export function usePolicy(id: number | null) {
  return useQuery({
    queryKey: ['precheck', 'policies', 'one', id],
    enabled: id !== null,
    queryFn: async () => (await apiClient.get<PrecheckPolicy>(`/precheck/policies/${id}/`)).data,
    // A revision from feedback arrives a few seconds later.
    refetchInterval: (q) => (q.state.data?.feedback?.some((f) => f.status === 'revising') ? 3000 : false),
  })
}

export function useSavePolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...payload }: Partial<PolicyInput> & { id?: number }) =>
      (id ? await apiClient.patch<PrecheckPolicy>(`/precheck/policies/${id}/`, payload) : await apiClient.post<PrecheckPolicy>('/precheck/policies/', payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', 'policies'] }),
  })
}

export function useDeletePolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/precheck/policies/${id}/`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', 'policies'] }),
  })
}

/** Feedback on a policy: the AI revises the policy from it, keeping the old wording. */
export function usePolicyFeedback() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; text: string; task?: string; context?: string }) =>
      (await apiClient.post<PolicyFeedback>(`/precheck/policies/${id}/feedback/`, payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['precheck', 'policies'] }),
  })
}
