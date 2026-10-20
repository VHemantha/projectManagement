import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

export interface AnswerSource {
  id: string
  label: string
  /** How it was found: "tags + meaning", "meaning" or words "…" (an exact match). */
  how: string
  evidence: { file_name?: string; location?: string; quote: string; drive_url?: string } | null
}

/** Where a point of an answer comes from: this task's documents (cited), New Zealand standards and
 * law (with the reference), or general knowledge beyond them (with what and where). */
export type AnswerBasis = 'task_documents' | 'nz_standards_law' | 'general_knowledge'

export interface AnswerPoint {
  text: string
  basis: AnswerBasis
  reference: string
  sources: AnswerSource[]
  flags: string[]
}

export interface AssistantQuestion {
  id: string
  question: string
  status: 'pending' | 'answered' | 'failed'
  answer: string
  answer_status: '' | 'answered' | 'partial' | 'not_found'
  sources: AnswerSource[]
  flags: string[]
  /** Answers from 18 Oct 2026: each point with its basis. */
  points?: AnswerPoint[]
  outside_job?: boolean
  beyond_nz?: boolean
  failure_reason: string
  asked_by: string
  created_at: string
  answered_at: string | null
}

const POLL_MS = 2500

export function useConversation(jobKey: string) {
  return useQuery({
    queryKey: ['precheck', jobKey, 'ask'],
    queryFn: async () => (await apiClient.get<{ questions: AssistantQuestion[] }>(`/precheck/jobs/${jobKey}/ask/`)).data,
    refetchInterval: (query) => (query.state.data?.questions.some((q) => q.status === 'pending') ? POLL_MS : false),
  })
}

/** Stop waiting for an answer; one that arrives later is ignored. */
export function useStopQuestion(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (questionId: string) => (await apiClient.post<AssistantQuestion>(`/precheck/questions/${questionId}/stop/`)).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'ask'] }),
  })
}

export function useAsk(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (question: string) => (await apiClient.post<AssistantQuestion>(`/precheck/jobs/${jobKey}/ask/`, { question })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'ask'] }),
  })
}
