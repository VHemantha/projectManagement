import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

export interface ClientItem {
  id: number
  name: string
  logo: string | null
  primary_contact_name: string
  primary_contact_email: string
  notes: string
  /** On: every job must belong to a project. Off: jobs can be added for the client directly. */
  requires_projects: boolean
  project_count: number
  /** Key of the client's automatic job list, once it has one. */
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
    }) => {
      const { data } = await apiClient.post<ClientItem>('/clients/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['clients'] }),
  })
}

export function useUpdateClient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...patch }: { id: number } & Partial<Omit<ClientItem, 'id'>>) => {
      const { data } = await apiClient.patch<ClientItem>(`/clients/${id}/`, patch)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['clients'] }),
  })
}
