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

/** When the standard sub-tasks of a task starting today would be due (working days, holidays). */
export function useStageDates(enabled = true) {
  return useQuery({
    queryKey: ['stage-dates'],
    enabled,
    staleTime: 60 * 60 * 1000,
    queryFn: async () => (await apiClient.get<{ start: string; stages: { name: string; due_date: string | null }[] }>('/issues/stage-dates/')).data,
  })
}

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
  /** A team's own + contributing projects; a Group (top-level team) includes its sub-teams. */
  team?: number
  /** With `team`: only that team's own projects, not its sub-teams'. */
  exclude_sub_teams?: boolean
  /** Projects with no primary or contributing team. */
  no_team?: boolean
  client?: number
  /** Projects with no client (internal). */
  no_client?: boolean
  /** Also list archived jobs (hidden by default). */
  include_archived?: boolean
  /** Only archived jobs. */
  archived?: boolean
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
  /** Omit and send client_id instead for a client that doesn't require projects. */
  project?: string
  client_id?: number
  summary: string
  /** Free-text group the task belongs to. */
  group?: string
  /** Also add the standard sub-tasks (Pre-check, Preparation, Internal Review, Client Review). */
  default_subtasks?: boolean
  issue_type_id: number
  description?: Record<string, unknown> | null
  status_id?: number
  /** From a board column across projects: the server picks the project's status in this category. */
  status_category?: 'todo' | 'in_progress' | 'done'
  priority?: string
  assignee_id?: number | null
  reporter_id?: number | null
  epic_id?: number | null
  sprint_id?: number | null
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
    onSuccess: (data, payload) => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['projects', data.project] })
      // A first project-less job creates the client's job list.
      if (payload.client_id) {
        queryClient.invalidateQueries({ queryKey: ['clients'] })
        queryClient.invalidateQueries({ queryKey: ['projects'] })
      }
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

/** Archive or restore several jobs (and their sub-tasks) at once. */
export function useBulkArchive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ keys, archived }: { keys: string[]; archived: boolean }) => {
      const { data } = await apiClient.post<{ updated: number }>('/issues/archive/', { keys, archived })
      return data
    },
    onSuccess: (_data, { keys }) => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      for (const key of keys) queryClient.invalidateQueries({ queryKey: ['issue', key] })
    },
  })
}

/** One row of a bulk CSV upload, as the server checked it. */
export interface ImportRowResult {
  row: number
  key: string
  summary: string
  action: 'create' | 'update' | 'unchanged'
  /** Problems by column; empty when the row is fine. */
  errors: Record<string, string>
}

export interface ImportResult {
  rows: number
  failed: number
  create: number
  update: number
  unchanged: number
  /** False after a check, or when any row had a problem (then nothing was saved). */
  imported: boolean
  results: ImportRowResult[]
}

/** Tasks in bulk from the CSV template: `commit: false` only checks the file. */
export function useImportTasks() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, commit }: { file: File; commit: boolean }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('commit', commit ? 'true' : 'false')
      const { data } = await apiClient.post<ImportResult>('/issues/import/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return data
    },
    onSuccess: (data) => {
      if (!data.imported) return
      for (const key of ['issues', 'issue', 'projects', 'clients']) queryClient.invalidateQueries({ queryKey: [key] })
    },
  })
}

/** The tasks matching `params`, downloaded in the template's format to edit and upload again. */
export async function downloadTasksCsv(params: Record<string, string | number | boolean>) {
  const { data } = await apiClient.get<Blob>('/issues/export/', { params, responseType: 'blob' })
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = `tasks-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

/** Delete a task permanently, with its sub-tasks (team lead and above). */
export function useDeleteIssue() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (key: string) => {
      await apiClient.delete(`/issues/${key}/`)
      return key
    },
    onSuccess: (key) => {
      queryClient.removeQueries({ queryKey: ['issue', key] })
      for (const k of ['issues', 'projects', 'reports']) queryClient.invalidateQueries({ queryKey: [k] })
    },
  })
}
