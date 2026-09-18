import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import { type CurrentUser, useAuthStore } from '@/store/authStore'

interface AuthResponse {
  user: CurrentUser
  tokens: { access: string; refresh: string }
}

export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession)
  return useMutation({
    mutationFn: async (payload: { email: string; password: string }) => {
      const { data } = await apiClient.post<AuthResponse>('/auth/login/', payload)
      return data
    },
    onSuccess: (data) => setSession(data.tokens, data.user),
  })
}

export function useSignup() {
  const setSession = useAuthStore((s) => s.setSession)
  return useMutation({
    mutationFn: async (payload: {
      email: string
      username: string
      password: string
      display_name?: string
    }) => {
      const { data } = await apiClient.post<AuthResponse>('/auth/signup/', payload)
      return data
    },
    onSuccess: (data) => setSession(data.tokens, data.user),
  })
}

export function useCurrentUser() {
  const accessToken = useAuthStore((s) => s.accessToken)
  const setUser = useAuthStore((s) => s.setUser)
  return useQuery({
    queryKey: ['me'],
    enabled: !!accessToken,
    queryFn: async () => {
      const { data } = await apiClient.get<CurrentUser>('/auth/me/')
      setUser(data)
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useUpdateProfile() {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: FormData) => {
      const { data } = await apiClient.patch<CurrentUser>('/auth/me/', payload, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return data
    },
    onSuccess: (data) => {
      setUser(data)
      queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout)
  const queryClient = useQueryClient()
  return () => {
    logout()
    queryClient.clear()
  }
}
