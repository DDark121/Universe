import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from 'react'

import type { AuthSession, RoleCode } from '@/shared/api/types'
import { bindAuthBridge } from '@/shared/api/http'
import * as authApi from '@/shared/api/authApi'
import { clearSession, getRefreshToken, loadSession, saveSession } from '@/shared/auth/session'

type AuthContextValue = {
  session: AuthSession | null
  isReady: boolean
  isAuthenticated: boolean
  roles: RoleCode[]
  login: (payload: { username: string; password: string; otp_code?: string }) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  updatePassword: (currentPassword: string, newPassword: string) => Promise<void>
  setup2fa: () => Promise<{ secret: string; provisioning_uri: string }>
  enable2fa: (code: string) => Promise<void>
  disable2fa: (code: string) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const ROLE_CODES: RoleCode[] = ['student', 'teacher', 'admin', 'curator']

function normalizeRoles(input: string[]): RoleCode[] {
  return input.filter((role): role is RoleCode => ROLE_CODES.includes(role as RoleCode))
}

function buildSessionFromTokenPair(
  pair: authApi.TokenPairResponse,
  previous: AuthSession | null,
  user: authApi.MeResponse | null,
): AuthSession {
  return {
    accessToken: pair.access_token,
    refreshToken: pair.refresh_token,
    accessExpiresAt: pair.access_expires_at,
    mustChangePassword: pair.password_change_required,
    user: user
      ? {
          id: user.id,
          username: user.username,
          full_name: user.full_name,
          email: user.email,
          phone_number: user.phone_number,
          roles: normalizeRoles(user.roles),
          is_active: user.is_active,
          must_change_password: user.must_change_password,
        }
      : previous?.user ?? null,
  }
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<AuthSession | null>(() => loadSession())
  const bootSessionRef = useRef<AuthSession | null>(session)
  const [isReady, setIsReady] = useState(false)

  const syncSession = useCallback((next: AuthSession | null) => {
    setSession(next)
    saveSession(next)
  }, [])

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken()
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken)
      } catch {
        // Ignore server-side logout errors; local cleanup still required.
      }
    }
    clearSession()
    setSession(null)
  }, [])

  const refresh = useCallback(async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) {
      throw new Error('Нет refresh токена')
    }

    const pair = await authApi.refresh(refreshToken)
    syncSession(buildSessionFromTokenPair(pair, session, null))
    const me = await authApi.me()
    syncSession(buildSessionFromTokenPair(pair, loadSession(), me))
  }, [session, syncSession])

  const login = useCallback(
    async (payload: { username: string; password: string; otp_code?: string }) => {
      const pair = await authApi.login(payload)
      syncSession(buildSessionFromTokenPair(pair, session, null))
      const me = await authApi.me()
      syncSession(buildSessionFromTokenPair(pair, loadSession(), me))
    },
    [session, syncSession],
  )

  const updatePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      await authApi.changePassword(currentPassword, newPassword)
      const next = loadSession()
      if (next) {
        const updated: AuthSession = {
          ...next,
          mustChangePassword: false,
          user: next.user ? { ...next.user, must_change_password: false } : null,
        }
        syncSession(updated)
      }
    },
    [syncSession],
  )

  const setup2fa = useCallback(async () => {
    return authApi.setup2fa()
  }, [])

  const enable2fa = useCallback(async (code: string) => {
    await authApi.enable2fa(code)
  }, [])

  const disable2fa = useCallback(async (code: string) => {
    await authApi.disable2fa(code)
  }, [])

  useEffect(() => {
    bindAuthBridge({
      refresh,
      onRefreshFail: () => {
        void logout()
      },
    })
  }, [logout, refresh])

  useEffect(() => {
    let alive = true
    ;(async () => {
      const bootSession = bootSessionRef.current
      if (!bootSession) {
        if (alive) setIsReady(true)
        return
      }

      try {
        const me = await authApi.me()
        if (!alive) return
        const nextSession: AuthSession = {
          ...bootSession,
          user: {
            id: me.id,
            username: me.username,
            full_name: me.full_name,
            email: me.email,
            phone_number: me.phone_number,
            roles: normalizeRoles(me.roles),
            is_active: me.is_active,
            must_change_password: me.must_change_password,
          },
          mustChangePassword: me.must_change_password,
        }
        setSession(nextSession)
        saveSession(nextSession)
      } catch {
        if (alive) {
          clearSession()
          setSession(null)
        }
      } finally {
        if (alive) setIsReady(true)
      }
    })()

    return () => {
      alive = false
    }
  }, [])

  const roles = useMemo<RoleCode[]>(() => session?.user?.roles ?? [], [session?.user?.roles])
  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isReady,
      isAuthenticated: Boolean(session?.accessToken),
      roles,
      login,
      logout,
      refresh,
      updatePassword,
      setup2fa,
      enable2fa,
      disable2fa,
    }),
    [disable2fa, enable2fa, isReady, login, logout, refresh, roles, session, setup2fa, updatePassword],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('Auth context is unavailable')
  }
  return context
}
