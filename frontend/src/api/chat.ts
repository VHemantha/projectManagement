import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { Channel, ChatMessage, IssueDetail, Paginated, User } from './types'

export function useChannels() {
  return useQuery({
    queryKey: ['chat', 'channels'],
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<Channel>>('/chat/channels/')
      return data.results
    },
    refetchInterval: 30_000,
  })
}

export function useChannel(channelId: number | undefined) {
  return useQuery({
    queryKey: ['chat', 'channels', channelId],
    enabled: !!channelId,
    queryFn: async () => {
      const { data } = await apiClient.get<Channel>(`/chat/channels/${channelId}/`)
      return data
    },
  })
}

export function useChannelMembers(channelId: number | undefined) {
  return useQuery({
    queryKey: ['chat', 'channels', channelId, 'members'],
    enabled: !!channelId,
    queryFn: async () => {
      const { data } = await apiClient.get<User[]>(`/chat/channels/${channelId}/members/`)
      return data
    },
    staleTime: 60_000,
  })
}

export function useCreateChannel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; description?: string; channel_type: string; is_private?: boolean; member_ids?: number[] }) => {
      const { data } = await apiClient.post<Channel>('/chat/channels/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chat', 'channels'] }),
  })
}

export function useMarkChannelRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (channelId: number) => {
      await apiClient.post(`/chat/channels/${channelId}/mark-read/`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chat', 'channels'] }),
  })
}

export function useMessages(channelId: number | undefined) {
  return useQuery({
    queryKey: ['chat', 'channels', channelId, 'messages'],
    enabled: !!channelId,
    queryFn: async () => {
      const { data } = await apiClient.get<ChatMessage[]>(`/chat/channels/${channelId}/messages/`)
      return data
    },
  })
}

export function useLoadOlderMessages(channelId: number | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (beforeId: number) => {
      const { data } = await apiClient.get<ChatMessage[]>(`/chat/channels/${channelId}/messages/`, {
        params: { before: beforeId },
      })
      return data
    },
    onSuccess: (older) => {
      queryClient.setQueryData<ChatMessage[] | undefined>(['chat', 'channels', channelId, 'messages'], (prev) => [
        ...older,
        ...(prev ?? []),
      ])
    },
  })
}

export function useThreadReplies(messageId: number | undefined) {
  return useQuery({
    queryKey: ['chat', 'messages', messageId, 'replies'],
    enabled: !!messageId,
    queryFn: async () => {
      const { data } = await apiClient.get<ChatMessage[]>(`/chat/messages/${messageId}/replies/`)
      return data
    },
  })
}

export function useToggleReaction(channelId: number | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ messageId, emoji, add }: { messageId: number; emoji: string; add: boolean }) => {
      const { data } = await apiClient.request<ChatMessage>({
        url: `/chat/messages/${messageId}/reactions/`,
        method: add ? 'post' : 'delete',
        data: { emoji },
      })
      return data
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<ChatMessage[] | undefined>(
        ['chat', 'channels', channelId, 'messages'],
        (prev) => prev?.map((m) => (m.id === updated.id ? updated : m)),
      )
    },
  })
}

export function useCreateTaskFromMessage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      messageId,
      ...payload
    }: {
      messageId: number
      project: string
      summary: string
      issue_type_id: number
      description?: Record<string, unknown> | null
    }) => {
      const { data } = await apiClient.post<{ issue: IssueDetail; system_message: ChatMessage }>(
        `/chat/messages/${messageId}/create-task/`,
        payload,
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['chat'] })
    },
  })
}

/** Sends a message with a file attached. Goes over REST (not the WebSocket) because the
 * attachment upload needs a real message id to attach to; the backend broadcasts the
 * REST-created message to the channel group itself, so other connected clients still see
 * it live (see apps.chat.views.broadcast_message). */
export function useSendMessageWithAttachment(channelId: number | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ body, file }: { body: Record<string, unknown>; file: File }) => {
      const { data: message } = await apiClient.post<ChatMessage>(`/chat/channels/${channelId}/messages/`, {
        body,
      })
      const form = new FormData()
      form.append('file', file)
      const { data: attachment } = await apiClient.post(`/chat/messages/${message.id}/attachments/`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return { ...message, attachments: [attachment] } as ChatMessage
    },
    onSuccess: (message) => {
      queryClient.setQueryData<ChatMessage[] | undefined>(
        ['chat', 'channels', channelId, 'messages'],
        (prev) => {
          if (!prev) return [message]
          if (prev.some((m) => m.id === message.id)) return prev
          return [...prev, message]
        },
      )
    },
  })
}

export function useLinkTaskToMessage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ messageId, issueId }: { messageId: number; issueId: number }) => {
      const { data } = await apiClient.post(`/chat/messages/${messageId}/link-task/`, { issue_id: issueId })
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['chat'] }),
  })
}
