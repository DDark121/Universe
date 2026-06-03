import { Navigate, Outlet, useLocation } from 'react-router-dom'

import type { RoleCode } from '@/shared/api/types'
import { useAuth } from '@/shared/auth/AuthContext'
import { getDefaultRoute } from '@/shared/auth/defaultRoute'

export function RequireAuth() {
  const { isReady, isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isReady) {
    return <div className="page-wrap">Загрузка...</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}

export function RequireRoles({ roles }: { roles: RoleCode[] }) {
  const { session } = useAuth()
  const userRoles = session?.user?.roles ?? []
  if (!roles.some((role) => userRoles.includes(role))) {
    return <Navigate to={getDefaultRoute(userRoles)} replace />
  }
  return <Outlet />
}

export function RequirePasswordChange() {
  const { session } = useAuth()
  if (session?.mustChangePassword) {
    return <Navigate to="/password-change" replace />
  }
  return <Outlet />
}
