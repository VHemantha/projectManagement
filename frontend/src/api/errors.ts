import { AxiosError } from 'axios'

export function extractErrorMessage(error: unknown, fallback = 'Something went wrong.'): string {
  if (error instanceof AxiosError) {
    const data = error.response?.data
    if (typeof data === 'string') return data
    if (data && typeof data === 'object') {
      if ('detail' in data && typeof data.detail === 'string') return data.detail
      const firstKey = Object.keys(data)[0]
      if (firstKey) {
        const val = (data as Record<string, unknown>)[firstKey]
        if (Array.isArray(val)) return `${firstKey}: ${val[0]}`
        if (typeof val === 'string') return val
      }
    }
  }
  return fallback
}
