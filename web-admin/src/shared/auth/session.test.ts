import { describe, expect, it } from 'vitest'

import type { AuthSession } from '@/shared/api/types'
import { clearSession, getAccessToken, getRefreshToken, loadSession, saveSession } from '@/shared/auth/session'

describe('auth session storage', () => {
  it('stores and restores session', () => {
    const sample: AuthSession = {
      accessToken: 'a',
      refreshToken: 'r',
      accessExpiresAt: '2026-01-01T00:00:00Z',
      mustChangePassword: false,
      user: {
        id: '1',
        username: 'admin',
        full_name: 'Admin',
        email: 'admin@local',
        phone_number: '+70000000000',
        roles: ['admin'],
        is_active: true,
        must_change_password: false,
      },
    }

    saveSession(sample)
    expect(loadSession()).toEqual(sample)
    expect(getAccessToken()).toBe('a')
    expect(getRefreshToken()).toBe('r')

    clearSession()
    expect(loadSession()).toBeNull()
  })
})
