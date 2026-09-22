import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

export interface ClientItem {
  id: number
  name: string
  logo: string | null
  primary_contact_name: string
  primary_contact_email: string
  notes: string
  project_count: number
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
    mutationFn: async (payload: { name: string; primary_contact_name?: string; primary_contact_email?: string }) => {
      const { data } = await apiClient.post<ClientItem>('/clients/', payload)
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['clients'] }),
  })
}
