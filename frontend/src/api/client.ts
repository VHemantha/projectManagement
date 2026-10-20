import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

import { useAuthStore } from '@/store/authStore'

export const apiClient = axios.create({
  baseURL: '/api',
})

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refresh = useAuthStore.getState().refreshToken
  if (!refresh) return null
  try {
    const { data } = await axios.post('/api/auth/refresh/', { refresh })
    useAuthStore.getState().setAccessToken(data.access)
    return data.access as string
  } catch {
    useAuthStore.getState().logout()
    return null
  }
}

function refreshOnce(): Promise<string | null> {
  refreshPromise ??= refreshAccessToken().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

/** True when the token has expired or will within `marginSeconds` (read from the token itself). */
export function tokenExpiresSoon(token: string, marginSeconds = 30): boolean {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const { exp } = JSON.parse(atob(part.padEnd(part.length + ((4 - (part.length % 4)) % 4), '='))) as { exp?: number }
    return typeof exp === 'number' && exp * 1000 - Date.now() < marginSeconds * 1000
  } catch {
    return false
  }
}

/** Whether a WebSocket may connect with this token. A socket never gets a 401 to trigger the
 * refresh below, so with an expired token it would be refused and retry for ever. Instead the
 * token is refreshed here and false returned: the new token re-runs the socket hooks, which then
 * connect with it (or the person is signed out if the refresh fails). */
export function readyForSocket(token: string): boolean {
  if (!tokenExpiresSoon(token)) return true
  void refreshOnce()
  return false
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true
      const newToken = await refreshOnce()
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`
        return apiClient(original)
      }
    }
    return Promise.reject(error)
  },
)
