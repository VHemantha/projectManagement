import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

export type InvitationRole = 'admin' | 'worker'
export type InvitationStatus = 'pending' | 'accepted' | 'revoked' | 'expired'

export interface Invitation {
  id: number
  email: string
  role: InvitationRole
  team_id: number | null
  team_name: string | null
  invited_by_name: string | null
  status: InvitationStatus
  created_at: string
  sent_at: string
  expires_at: string
  accepted_at: string | null
  revoked_at: string | null
}

/** Returned when an invitation is sent or resent: the link (shown only then) and whether the
 * email went out. */
export interface SentInvitation extends Invitation {
  invite_url: string
  email_sent: boolean
}

export interface InvitationPreview {
  email: string
  role: InvitationRole
  team_name: string | null
  invited_by_name: string | null
  expires_at: string
}

export function useInvitations(enabled = true) {
  return useQuery({
    queryKey: ['invitations'],
    enabled,
    queryFn: async () => (await apiClient.get<Invitation[]>('/invitations/')).data,
  })
}

export function useCreateInvitation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { email: string; role: InvitationRole; team_id: number | null }) =>
      (await apiClient.post<SentInvitation>('/invitations/', payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['invitations'] }),
  })
}

export function useResendInvitation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => (await apiClient.post<SentInvitation>(`/invitations/${id}/resend/`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['invitations'] }),
  })
}

export function useRevokeInvitation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => (await apiClient.post<Invitation>(`/invitations/${id}/revoke/`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['invitations'] }),
  })
}

/** What an invitation link is for (public; no sign-in needed). */
export function useInvitationPreview(token: string | null) {
  return useQuery({
    queryKey: ['invitation-preview', token],
    enabled: !!token,
    retry: false,
    queryFn: async () => (await apiClient.get<InvitationPreview>(`/auth/invitations/${token}/`)).data,
  })
}
