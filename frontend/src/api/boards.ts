import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { BoardConfig, WorkflowTransitionItem } from './types'

export function useBoardConfig(boardId: number | undefined) {
  return useQuery({
    queryKey: ['boards', boardId, 'config'],
    enabled: !!boardId,
    queryFn: async () => {
      const { data } = await apiClient.get<BoardConfig>(`/boards/${boardId}/config/`)
      return data
    },
  })
}

export function useUpdateBoardConfig(boardId: number | undefined, projectKey: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (patch: Partial<Omit<BoardConfig, 'id'>>) => {
      const { data } = await apiClient.patch<BoardConfig>(`/boards/${boardId}/config/`, patch)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['boards', boardId, 'config'] })
      // The live board reads column_config/swimlane_mode/card_fields off the project-board
      // endpoint, not the config endpoint — invalidate that too so the board re-renders.
      if (projectKey) queryClient.invalidateQueries({ queryKey: ['projects', projectKey, 'board'] })
    },
  })
}

export function useWorkflowTransitions(projectKey: string | undefined) {
  return useQuery({
    queryKey: ['projects', projectKey, 'workflow-transitions'],
    enabled: !!projectKey,
    queryFn: async () => {
      const { data } = await apiClient.get<WorkflowTransitionItem[]>(`/projects/${projectKey}/workflow/transitions/`)
      return data
    },
  })
}

export function useUpdateWorkflowTransition(projectKey: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, set_current_responsible_to }: { id: number; set_current_responsible_to: string }) => {
      const { data } = await apiClient.patch<WorkflowTransitionItem>(`/workflow-transitions/${id}/`, {
        set_current_responsible_to,
      })
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects', projectKey, 'workflow-transitions'] }),
  })
}
