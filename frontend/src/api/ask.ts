import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

export interface AnswerSource {
  id: string
  label: string
  /** How it was found: "tags + meaning", "meaning" or words "…" (an exact match). */
  how: string
  evidence: { file_name?: string; location?: string; quote: string; drive_url?: string } | null
}

export interface AssistantQuestion {
  id: string
  question: string
  status: 'pending' | 'answered' | 'failed'
  answer: string
  answer_status: '' | 'answered' | 'partial' | 'not_found'
  sources: AnswerSource[]
  flags: string[]
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

export function useAsk(jobKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (question: string) => (await apiClient.post<AssistantQuestion>(`/precheck/jobs/${jobKey}/ask/`, { question })).data,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['precheck', jobKey, 'ask'] }),
  })
}
