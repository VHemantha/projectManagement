import { useQuery } from '@tanstack/react-query'

import { apiClient } from './client'
import type { User } from './types'

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
