import type { ProjectDetail } from '@/api/types'
import { useAuthStore } from '@/store/authStore'

/** Mirrors the backend's _can_configure_board: staff, the project lead, or a project admin. */
export function useCanConfigureBoard(project: ProjectDetail): boolean {
  const currentUser = useAuthStore((s) => s.user)
  if (!currentUser) return false
  return (
    currentUser.is_staff ||
    project.lead?.id === currentUser.id ||
    project.memberships.some((m) => m.user.id === currentUser.id && m.role === 'admin')
  )
}
