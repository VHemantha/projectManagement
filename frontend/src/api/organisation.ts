import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { ClientItem } from './clients'
import type { Paginated, ProjectSummary, TeamSummary, User } from './types'

export interface Organisation {
  id: number
  name: string
  /** Only the CEO may rename it. */
  can_edit: boolean
}

export function useOrganisation() {
  return useQuery({
    queryKey: ['organization'],
    queryFn: async () => (await apiClient.get<Organisation>('/organization/')).data,
    staleTime: 5 * 60_000,
  })
}

/** Everything with a name in the organisation, for the CEO's Names tab: all of each, unpaged. */
export function useOrganisationNames() {
  return useQuery({
    queryKey: ['organization', 'names'],
    queryFn: async () => {
      const [people, teams, clients, projects] = await Promise.all([
        apiClient.get<User[]>('/users/'),
        apiClient.get<Paginated<TeamSummary>>('/teams/', { params: { page_size: 1000 } }),
        apiClient.get<ClientItem[]>('/clients/'),
        apiClient.get<Paginated<ProjectSummary>>('/projects/', { params: { page_size: 1000, is_archived: false } }),
      ])
      return { people: people.data, teams: teams.data.results, clients: clients.data, projects: projects.data.results }
    },
  })
}

export type Renamable = 'organisation' | 'person' | 'team' | 'client' | 'project'

const URLS: Record<Renamable, (id: number | string) => string> = {
  organisation: () => '/organization/',
  person: (id) => `/users/${id}/`,
  team: (id) => `/teams/${id}/`,
  client: (id) => `/clients/${id}/`,
  project: (key) => `/projects/${key}/`,
}

// What else on screen shows each kind of name.
const ALSO_SHOWN: Record<Renamable, unknown[][]> = {
  organisation: [['organization']],
  person: [['users'], ['me']],
  team: [['teams'], ['reports', 'nav-tree']],
  client: [['clients'], ['reports', 'nav-tree']],
  project: [['projects'], ['reports', 'nav-tree'], ['issues']],
}

/** Rename one thing: {display_name, job_title} for a person, {name} for the rest. */
export function useRename(kind: Renamable) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id: number | string; body: Record<string, string> }) =>
      (await apiClient.patch(URLS[kind](id), body)).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['organization'] })
      for (const queryKey of ALSO_SHOWN[kind]) void queryClient.invalidateQueries({ queryKey })
    },
  })
}
