import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Run, Severity, SourceRef } from './precheck'

export type ReviewResponseKind = 'agree' | 'fixed' | 'not_an_issue' | 'wrong_reason'
export type AssumptionVerdict = 'supported' | 'challenged' | 'needs_evidence'

export interface Assumption {
  id: number
  ref: string
  area: string
  area_label: string
  fs_line: string
  amount: string
  judgement: string
  basis: string
  evidence: string
  status: 'active' | 'withdrawn'
  history: Record<string, string>[]
  created_by: string
  updated_by: string
  updated_at: string
}

export interface ReviewFindingRecord {
  id: number
  ref: string
  origin: 'ai' | 'person'
  area: string
  fs_line: string
  issue: string
  why: string
  action: string
  severity: Severity
  sources: SourceRef[]
  assumptions: string[]
  flags: string[]
  status: 'open' | 'resolved' | 'closed'
  resolved_reason: string
  response: ReviewResponseKind | ''
  note: string
  responded_by: string
  responded_at: string | null
  responses: { response: ReviewResponseKind; note: string; by: string; at: string }[]
  created_by: string
  created_at: string
}

/** One review round's output, as the agent sent it (findings carry the refs the app gave them). */
export interface ReviewOutput {
  decision: { state: 'findings' | 'clear' | 'blocked'; label: string; reason: string }
  summary: string
  draft_fs: { name: string; evidence_id: string | null }[]
  draft_found_by: '' | 'folder' | 'task card'
  findings: { ref: string; severity: Severity; issue: string }[]
  resolved: { ref: string; reason: string; sources: SourceRef[] }[]
  assumption_reviews: { assumption: string; verdict: AssumptionVerdict; reason: string; sources: SourceRef[] }[]
  lessons_applied: { id: string; text: string }[]
  checks: { label: string; passed: boolean; detail: string }[]
  counts: Record<Severity, number>
  evidence: Record<string, { file_name: string; location: string; quote: string; drive_url: string }>
  how?: string
}

export interface ReviewState {
  session: { status: 'in_progress' | 'complete'; completed_by: string; completed_at: string | null; note: string }
  assumptions: Assumption[]
  findings: ReviewFindingRecord[]
  latest: (Run & { kind: string; review: ReviewOutput | Record<string, never> }) | null
  rounds: { run_id: string; status: string; created_at: string; requested_by: string; decision?: ReviewOutput['decision'] }[]
  open_high: number
  can_complete: boolean
  areas: { value: string; label: string }[]
  rounds_done: number
}

export type AssumptionInput = Partial<Pick<Assumption, 'area' | 'fs_line' | 'amount' | 'judgement' | 'basis' | 'evidence' | 'status'>>

const POLL_MS = 4000

export function useJobReview(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'review'],
    queryFn: async () => (await apiClient.get<ReviewState>(`/precheck/jobs/${jobKey}/review/`)).data,
    refetchInterval: (query) => (query.state.data?.latest?.status === 'running' ? POLL_MS : false),
  })
}

function useReviewMutation<T>(jobKey: string, fn: (body: T) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'review'] }),
  })
}

export function useRunReview(jobKey: string) {
  return useReviewMutation<void>(jobKey, async () => (await apiClient.post(`/precheck/jobs/${jobKey}/review/runs/`, {})).data)
}

export function useSaveAssumption(jobKey: string) {
  return useReviewMutation<{ id?: number; body: AssumptionInput }>(jobKey, async ({ id, body }) =>
    id
      ? (await apiClient.patch(`/precheck/assumptions/${id}/`, body)).data
      : (await apiClient.post(`/precheck/jobs/${jobKey}/assumptions/`, body)).data,
  )
}

export function useRespondToFinding(jobKey: string) {
  return useReviewMutation<{ id: number; response: ReviewResponseKind; note: string }>(jobKey, async ({ id, ...body }) =>
    (await apiClient.post(`/precheck/review-findings/${id}/respond/`, body)).data,
  )
}

export function useAddMissed(jobKey: string) {
  return useReviewMutation<{ area: string; fs_line: string; issue: string; note: string }>(jobKey, async (body) =>
    (await apiClient.post(`/precheck/jobs/${jobKey}/review/missed/`, body)).data,
  )
}

export function useCompleteReview(jobKey: string) {
  return useReviewMutation<{ note?: string; reopen?: boolean }>(jobKey, async (body) =>
    (await apiClient.post(`/precheck/jobs/${jobKey}/review/complete/`, body)).data,
  )
}
