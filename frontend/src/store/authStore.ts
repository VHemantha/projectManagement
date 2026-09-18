import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface CurrentUser {
  id: number
  email: string
  username: string
  display_name: string
  job_title: string
  avatar: string | null
  is_staff: boolean
}

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: CurrentUser | null
  setSession: (tokens: { access: string; refresh: string }, user: CurrentUser) => void
  setAccessToken: (access: string) => void
  setUser: (user: CurrentUser) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setSession: (tokens, user) =>
        set({ accessToken: tokens.access, refreshToken: tokens.refresh, user }),
      setAccessToken: (access) => set({ accessToken: access }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    { name: 'trackflow-auth' },
  ),
)
