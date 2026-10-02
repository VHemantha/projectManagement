import { useQuery } from '@tanstack/react-query'

import { apiClient } from './client'
import type { User, UserHierarchy } from './types'

export function useUsers(q?: string) {
  return useQuery({
    queryKey: ['users', q ?? ''],
    queryFn: async () => {
      const { data } = await apiClient.get<User[]>('/users/', { params: q ? { q } : undefined })
      return data
    },
    staleTime: 60_000,
  })
}

export function useUserHierarchy(enabled = true) {
  return useQuery({
    queryKey: ['users', 'hierarchy'],
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<UserHierarchy>('/users/hierarchy/')
      return data
    },
    staleTime: 60_000,
  })
}
