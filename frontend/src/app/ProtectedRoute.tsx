import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuthStore } from '@/store/authStore'

export function ProtectedRoute() {
  const accessToken = useAuthStore((s) => s.accessToken)
  const location = useLocation()

  if (!accessToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
