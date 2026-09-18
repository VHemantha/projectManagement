import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { NotificationItem, Paginated } from './types'
import { useAuthStore } from '@/store/authStore'

const POLL_INTERVAL = 20_000

export function useNotifications() {
  const accessToken = useAuthStore((s) => s.accessToken)
  return useQuery({
    queryKey: ['notifications'],
    enabled: !!accessToken,
    refetchInterval: POLL_INTERVAL,
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<NotificationItem>>('/notifications/')
      return data.results
    },
  })
}

export function useUnreadCount() {
  const accessToken = useAuthStore((s) => s.accessToken)
  return useQuery({
    queryKey: ['notifications', 'unread-count'],
    enabled: !!accessToken,
    refetchInterval: POLL_INTERVAL,
    queryFn: async () => {
      const { data } = await apiClient.get<{ count: number }>('/notifications/unread-count/')
      return data.count
    },
  })
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await apiClient.patch(`/notifications/${id}/read/`, {})
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await apiClient.post('/notifications/mark-all-read/')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}
