import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { IssueMini, Paginated, ProjectSummary, SavedFilter } from './types'

export function useQuickSearch(q: string) {
  return useQuery({
    queryKey: ['quick-search', q],
    enabled: q.trim().length > 0,
    queryFn: async () => {
      const { data } = await apiClient.get<{ issues: IssueMini[]; projects: ProjectSummary[] }>(
        '/search/quick/',
        { params: { q } },
      )
      return data
    },
  })
}

export function useFilters() {
  return useQuery({
    queryKey: ['filters'],
    queryFn: async () => {
      const { data } = await apiClient.get<Paginated<SavedFilter>>('/search/filters/')
      return data.results
    },
  })
}

export function useCreateFilter() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; query: Record<string, unknown>; is_public?: boolean }) => {
      const { data } = await apiClient.post<SavedFilter>('/search/filters/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['filters'] }),
  })
}

export function useDeleteFilter() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/search/filters/${id}/`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['filters'] }),
  })
}
