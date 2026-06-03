import type { AuthSession } from '@/shared/api/types'

const AUTH_SESSION_KEY = 'universe_admin_auth_session'

export function loadSession(): AuthSession | null {
  try {
    const raw = localStorage.getItem(AUTH_SESSION_KEY)
    if (!raw) return null
    return JSON.parse(raw) as AuthSession
  } catch {
    return null
  }
}

export function saveSession(session: AuthSession | null) {
  if (!session) {
    localStorage.removeItem(AUTH_SESSION_KEY)
    return
  }
  localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session))
}

export function clearSession() {
  localStorage.removeItem(AUTH_SESSION_KEY)
}

export function getAccessToken(): string | null {
  return loadSession()?.accessToken ?? null
}

export function getRefreshToken(): string | null {
  return loadSession()?.refreshToken ?? null
}
