import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { apiClient } from './client'

export type SavedTableState = Record<string, unknown>
type Preferences = Record<string, SavedTableState>

const KEY = ['table-preferences']

/** Every table layout the current user has saved ({table_id: state}), loaded once. */
export function useTablePreferences() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<Preferences>('/auth/me/table-preferences/')
      return data
    },
    staleTime: Infinity,
  })
}

/** Save or reset (state = null) one table's layout, keeping the cached copy in step. */
export function useSaveTablePreference() {
  const queryClient = useQueryClient()
  return useCallback(
    async (tableId: string, state: SavedTableState | null) => {
      queryClient.setQueryData<Preferences>(KEY, (prev) => {
        const next = { ...(prev ?? {}) }
        if (state) next[tableId] = state
        else delete next[tableId]
        return next
      })
      if (state) await apiClient.put(`/auth/me/table-preferences/${tableId}/`, { state })
      else await apiClient.delete(`/auth/me/table-preferences/${tableId}/`)
    },
    [queryClient],
  )
}
