import axios, { AxiosError } from 'axios'
import { AxiosHeaders } from 'axios'
import { waitFor } from '@testing-library/react'

function jsonResponse(payload: unknown, status = 202) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('reports unexpected 5xx api errors and ignores expected 4xx responses', async () => {
  vi.resetModules()
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ message: 'accepted' }, 202))
  vi.stubGlobal('fetch', fetchMock)

  const { reportApiError } = await import('./clientLogger')

  const serverError = new AxiosError('Server failure')
  Object.assign(serverError, {
    response: { status: 500 },
    config: { method: 'get', url: '/users' },
  })
  reportApiError(serverError, { source: 'unit-test' })

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  const validationError = new AxiosError('Validation failure')
  Object.assign(validationError, {
    response: { status: 400 },
    config: { method: 'post', url: '/users' },
  })
  reportApiError(validationError, { source: 'unit-test' })

  await new Promise((resolve) => window.setTimeout(resolve, 0))
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('recognizes already reported axios errors', async () => {
  vi.resetModules()

  const { isErrorAlreadyReported, reportApiError } = await import('./clientLogger')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ message: 'accepted' }, 202)))

  const error = new AxiosError(
    'Network failed',
    undefined,
    {
      url: '/health',
      headers: new AxiosHeaders(),
      method: 'get',
    } as never,
    undefined,
    undefined,
  )
  expect(isErrorAlreadyReported(error)).toBe(false)

  reportApiError(error, { source: 'unit-test' })

  await waitFor(() => {
    expect(isErrorAlreadyReported(error)).toBe(true)
  })
  expect(axios.isAxiosError(error)).toBe(true)
})

it('copies axios headers without relying on forEach', async () => {
  vi.resetModules()

  const { withCorrelationHeaders } = await import('./clientLogger')
  const headers = new AxiosHeaders({
    'Content-Type': 'application/json',
    Authorization: 'Bearer token',
  })
  const originalForEach = AxiosHeaders.prototype.forEach
  ;(AxiosHeaders.prototype as AxiosHeaders & { forEach?: unknown }).forEach = undefined

  try {
    const next = withCorrelationHeaders(headers)

    expect(next.get('Content-Type')).toBe('application/json')
    expect(next.get('Authorization')).toBe('Bearer token')
    expect(next.get('X-Correlation-ID')).toBeTruthy()
  } finally {
    ;(AxiosHeaders.prototype as AxiosHeaders & { forEach?: unknown }).forEach = originalForEach
  }
})
