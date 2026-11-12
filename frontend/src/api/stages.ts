import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Comment, Paginated } from './types'

/** The task's five stages, in order, as the milestone bar shows them (AFIT, 12 Nov 2026). */
export type StageKey = 'precheck' | 'preparation' | 'internal_review' | 'client_review' | 'dispatch'

export interface TaskStage {
  key: StageKey
  label: string
  state: 'done' | 'active' | 'upcoming'
  /** When it was done (YYYY-MM-DD), else null. */
  done_on: string | null
  /** When it is due: its standard sub-task's date (Dispatch: the task's own). */
  due_date: string | null
  /** The stage's sub-task, if the task has one. */
  subtask: string | null
  /** Comments about this stage, the AI's posted results included. */
  comments: number
}

export interface StageNoteDraft {
  stage: StageKey
  label: string
  text: string
  /** True when Claude wrote it; false when code did (no key, or the daily cap reached). */
  ai: boolean
  facts: string[]
}

// Stages are under ['issues'] so any task change (a stage's sub-task finished) refreshes them; the
// live updates also refresh them on a new comment or an AI result (useLiveUpdates). Stage comments are
// under ['issue', key], refreshed by every new comment, the AI's posted results included.
export const stagesKey = (issueKey: string) => ['issues', 'stages', issueKey]
export const stageCommentsKey = (issueKey: string, stage: StageKey) => ['issue', issueKey, 'comments', 'stage', stage]

export function useTaskStages(issueKey: string) {
  return useQuery({
    queryKey: stagesKey(issueKey),
    queryFn: async () => (await apiClient.get<{ stages: TaskStage[] }>(`/precheck/jobs/${issueKey}/stages/`)).data.stages,
  })
}

/** The stage's history: its comments, newest first. */
export function useStageComments(issueKey: string, stage: StageKey | null) {
  return useQuery({
    queryKey: stageCommentsKey(issueKey, stage ?? 'precheck'),
    enabled: !!stage,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<Comment>>(`/issues/${issueKey}/comments/`, { params: { stage, page_size: 200 } })
      return [...data.results].reverse()
    },
  })
}

export function useAddStageComment(issueKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ stage, body }: { stage: StageKey; body: Record<string, unknown> }) =>
      (await apiClient.post<Comment>(`/issues/${issueKey}/comments/`, { body, stage })).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['issue', issueKey, 'comments'] })
      void queryClient.invalidateQueries({ queryKey: stagesKey(issueKey) })
    },
  })
}

/** The AI's draft of a comment recording the stage's completion, from its latest results. Nothing is posted. */
export function useDraftStageNote(issueKey: string) {
  return useMutation({
    mutationFn: async (stage: StageKey) =>
      (await apiClient.post<StageNoteDraft>(`/precheck/jobs/${issueKey}/stage-note/`, { stage })).data,
  })
}

/** Plain text (one paragraph per line; "- " lines as bullets) as a rich-text comment body. */
export function textToDoc(text: string): Record<string, unknown> {
  const content: Record<string, unknown>[] = []
  let bullets: Record<string, unknown>[] = []
  const flush = () => {
    if (bullets.length) content.push({ type: 'bulletList', content: bullets })
    bullets = []
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) {
      flush()
      continue
    }
    const bullet = line.match(/^[-•*]\s+(.*)$/)
    const paragraph = { type: 'paragraph', content: [{ type: 'text', text: bullet ? bullet[1] : line }] }
    if (bullet) bullets.push({ type: 'listItem', content: [paragraph] })
    else {
      flush()
      content.push(paragraph)
    }
  }
  flush()
  return { type: 'doc', content }
}
