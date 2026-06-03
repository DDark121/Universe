import { describe, expect, it } from 'vitest'

import { formatDate, formatDateTime, humanizeStatus } from '@/shared/utils/format'

describe('format utils', () => {
  it('formats date and datetime', () => {
    expect(formatDate('2026-02-01T00:00:00Z')).toMatch(/01\.02\.2026/)
    expect(formatDateTime('2026-02-01T08:30:00Z')).toContain('01.02.2026')
  })

  it('handles empty values', () => {
    expect(formatDate(undefined)).toBe('-')
    expect(formatDateTime(null)).toBe('-')
  })

  it('humanizes statuses', () => {
    expect(humanizeStatus('in_progress')).toBe('In progress')
  })
})
