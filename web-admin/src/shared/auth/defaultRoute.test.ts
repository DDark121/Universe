import { describe, expect, it } from 'vitest'

import { getDefaultRoute } from '@/shared/auth/defaultRoute'

describe('getDefaultRoute', () => {
  it('sends teachers to teacher cabinet', () => {
    expect(getDefaultRoute(['teacher'])).toBe('/teacher/lessons')
  })

  it('prioritizes admin and curator dashboard', () => {
    expect(getDefaultRoute(['teacher', 'admin'])).toBe('/dashboard')
    expect(getDefaultRoute(['curator'])).toBe('/dashboard')
  })
})
