import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

/** A sub-workspace (the API and model call it a client): Workspace > Sub-workspace > Project > Task. */
export interface ClientItem {
  id: number
  name: string
  logo: string | null
  primary_contact_name: string
  primary_contact_email: string
  notes: string
  /** On: every task must belong to a project. Off: tasks can be added to the sub-workspace directly. */
  requires_projects: boolean
  /** The workspace (team) this sub-workspace is in. */
  team_id: number | null
  team_name: string | null
  project_count: number
  /** Key of the sub-workspace's automatic list of tasks without a project, once it has one. */
  workspace_project_key: string | null
  created_at: string
}

export function useClients() {
  return useQuery({
    queryKey: ['clients'],
    queryFn: async () => {
      const { data } = await apiClient.get<ClientItem[]>('/clients/')
      return data
    },
  })
}

export function useCreateClient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: {
      name: string
      primary_contact_name?: string
      primary_contact_email?: string
      requires_projects?: boolean
      team_id?: number | null
    }) => {
      const { data } = await apiClient.post<ClientItem>('/clients/', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      queryClient.invalidateQueries({ queryKey: ['reports', 'nav-tree'] })
    },
  })
}

export function useUpdateClient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...patch }: { id: number } & Partial<Omit<ClientItem, 'id'>>) => {
      const { data } = await apiClient.patch<ClientItem>(`/clients/${id}/`, patch)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      queryClient.invalidateQueries({ queryKey: ['reports', 'nav-tree'] })
    },
  })
}
