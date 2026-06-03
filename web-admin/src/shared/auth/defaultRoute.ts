import type { RoleCode } from '@/shared/api/types'

export function getDefaultRoute(roles: RoleCode[] | undefined) {
  const roleSet = new Set(roles ?? [])
  if (roleSet.has('admin') || roleSet.has('curator')) {
    return '/dashboard'
  }
  if (roleSet.has('teacher')) {
    return '/teacher/lessons'
  }
  return '/dashboard'
}
