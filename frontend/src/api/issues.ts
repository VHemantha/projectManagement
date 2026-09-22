import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type {
  Attachment,
  Comment,
  IssueChatLink,
  IssueDetail,
  IssueHistoryEntry,
  IssueLink,
  IssueListItem,
  IssueType,
  Paginated,
  RecentActivityEntry,
} from './types'

export function useIssueTypes(projectKey?: string, includeSubtasks = true) {
  return useQuery({
    queryKey: ['issue-types', projectKey ?? '', includeSubtasks],
    queryFn: async () => {
      const { data } = await apiClient.get<IssueType[]>('/issue-types/', {
        params: { project: projectKey, include_subtasks: includeSubtasks },
      })
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export interface IssueQueryParams {
  project?: string
  status_category?: string
  sprint?: number
  no_sprint?: boolean
  assignee?: number
  assignee_in?: string
  unassigned?: boolean
  reviewer?: number
  current_responsible?: number
  epic?: number
  parent?: number
  no_parent?: boolean
  issue_type?: string
  exclude_type?: string
  priority?: string
  search?: string
  ordering?: string
  page?: number
  page_size?: number
}

export function useIssues(params: IssueQueryParams, enabled = true) {
  return useQuery({
    queryKey: ['issues', params],
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<IssueListItem>>('/issues/', { params })
      return data
    },
  })
}

export function useIssue(key: string | undefined) {
  return useQuery({
    queryKey: ['issue', key],
    enabled: !!key,
    queryFn: async () => {
      const { data } = await apiClient.get<IssueDetail>(`/issues/${key}/`)
      return data
    },
  })
}

export interface CreateIssuePayload {
  project: string
  summary: string
  issue_type_id: number
  description?: Record<string, unknown> | null
  status_id?: number
  priority?: string
  assignee_id?: number | null
  epic_id?: number | null
  sprint_id?: number | null
  story_points?: number | null
  due_date?: string | null
  label_ids?: number[]
}

export function useCreateIssue() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CreateIssuePayload) => {
      const { data } = await apiClient.post<IssueDetail>('/issues/', payload)
      return data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['projects', data.project] })
    },
  })
}

export function useUpdateIssue(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: Record<string, unknown>) => {
      const { data } = await apiClient.patch<IssueDetail>(`/issues/${key}/`, payload)
      return data
    },
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: ['issue', key] })
      const previous = queryClient.getQueryData<IssueDetail>(['issue', key])
      if (previous) {
        queryClient.setQueryData(['issue', key], { ...previous, ...payload })
      }
      return { previous }
    },
    onError: (_err, _payload, context) => {
      if (context?.previous) queryClient.setQueryData(['issue', key], context.previous)
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['issue', key], data)
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['issue', key, 'history'] })
    },
  })
}

export interface MoveIssuePayload {
  before_id?: number | null
  after_id?: number | null
  sprint_id?: number | null
  status_id?: number
}

export function useMoveIssue() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ key, ...payload }: MoveIssuePayload & { key: string }) => {
      const { data } = await apiClient.post<IssueDetail>(`/issues/${key}/move/`, payload)
      return data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.setQueryData(['issue', data.key], data)
    },
  })
}

export function usePatchIssueField() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ key, patch }: { key: string; patch: Record<string, unknown> }) => {
      const { data } = await apiClient.patch<IssueDetail>(`/issues/${key}/`, patch)
      return data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.setQueryData(['issue', data.key], data)
    },
  })
}

export function useToggleWatch(key: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (watching: boolean) => {
      const { data } = await apiClient.request<{ is_watching: boolean }>({
        url: `/issues/${key}/watch/`,
        method: watching ? 'post' : 'delete',
      })
      return data
    },
    onSuccess: (data) => {
      queryClient.setQueryData<IssueDetail | undefined>(['issue', key], (prev) =>
        prev
          ? {
              ...prev,
              is_watching: data.is_watching,
              watcher_count: prev.watcher_count + (data.is_watching ? 1 : -1),
            }
          : prev,
      )
    },
  })
}

export function useComments(issueKey: string | undefined) {
  return useQuery({
    queryKey: ['issue', issueKey, 'comments'],
    enabled: !!issueKey,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<Comment>>(`/issues/${issueKey}/comments/`)
      return data.results
    },
  })
}

export function useAddComment(issueKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      const { data } = await apiClient.post<Comment>(`/issues/${issueKey}/comments/`, { body })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issue', issueKey, 'comments'] })
    },
  })
}

export function useIssueHistory(issueKey: string | undefined) {
  return useQuery({
    queryKey: ['issue', issueKey, 'history'],
    enabled: !!issueKey,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<IssueHistoryEntry>>(`/issues/${issueKey}/history/`)
      return data.results
    },
  })
}

export function useAddSubtask(issueKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (summary: string) => {
      const { data } = await apiClient.post<IssueDetail>(`/issues/${issueKey}/subtasks/`, { summary })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issue', issueKey] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
  })
}

export function useAttachments(issueKey: string | undefined) {
  return useQuery({
    queryKey: ['issue', issueKey, 'attachments'],
    enabled: !!issueKey,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<Attachment>>(`/issues/${issueKey}/attachments/`)
      return data.results
    },
  })
}

export function useUploadAttachment(issueKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const { data } = await apiClient.post<Attachment>(`/issues/${issueKey}/attachments/`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issue', issueKey, 'attachments'] })
    },
  })
}

export function useDeleteAttachment(issueKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/issues/${issueKey}/attachments/${id}/`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issue', issueKey, 'attachments'] })
    },
  })
}

export function useIssueChatLinks(issueKey: string | undefined) {
  return useQuery({
    queryKey: ['issue', issueKey, 'chat-links'],
    enabled: !!issueKey,
    queryFn: async () => {
      const { data } = await apiClient.get<IssueChatLink[]>(`/issues/${issueKey}/chat-links/`)
      return data
    },
  })
}

export function useRecentActivity() {
  return useQuery({
    queryKey: ['activity', 'recent'],
    queryFn: async () => {
      const { data } = await apiClient.get<RecentActivityEntry[]>('/activity/recent/')
      return data
    },
  })
}

export function useIssueLinks(issueKey: string | undefined) {
  return useQuery({
    queryKey: ['issue', issueKey, 'links'],
    enabled: !!issueKey,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<IssueLink>>(`/issues/${issueKey}/links/`)
      return data.results
    },
  })
}

export function useAddIssueLink(issueKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { target_issue_id: number; link_type: string }) => {
      const { data } = await apiClient.post<IssueLink>(`/issues/${issueKey}/links/`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issue', issueKey, 'links'] })
    },
  })
}

export function useRemoveIssueLink(issueKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (linkId: number) => {
      await apiClient.delete(`/issues/${issueKey}/links/${linkId}/`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issue', issueKey, 'links'] })
    },
  })
}
