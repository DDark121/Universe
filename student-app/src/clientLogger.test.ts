import { waitFor } from '@testing-library/react'

function jsonResponse(payload: unknown, status = 202, headers?: Record<string, string>) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...(headers || {}),
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('adds correlation headers and reports unexpected 5xx responses', async () => {
  vi.resetModules()

  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse({ error: 'boom' }, 500, { 'X-Correlation-ID': 'backend-correlation' }))
    .mockResolvedValueOnce(jsonResponse({ message: 'accepted' }, 202))
  vi.stubGlobal('fetch', fetchMock)

  const { trackedFetch, getCorrelationId } = await import('./clientLogger')
  const response = await trackedFetch('http://localhost:8000/api/v1/student/profile', undefined, {
    feature: 'test-case',
  })

  expect(response.status).toBe(500)
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
    headers: expect.any(Headers),
  })
  expect((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).toBeInstanceOf(Headers)
  const firstHeaders = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Headers
  expect(firstHeaders.get('X-Correlation-ID')).toBeTruthy()

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  const reportRequest = fetchMock.mock.calls[1]
  expect(reportRequest?.[0]).toContain('/public/client-errors')
  expect(getCorrelationId()).toBe('backend-correlation')
  expect(reportRequest?.[1]).toMatchObject({
    keepalive: true,
  })
})

it('reports global unhandled rejections', async () => {
  vi.resetModules()

  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ message: 'accepted' }, 202))
  vi.stubGlobal('fetch', fetchMock)

  const { installGlobalErrorHandlers } = await import('./clientLogger')
  installGlobalErrorHandlers()

  const event = new Event('unhandledrejection')
  Object.defineProperty(event, 'reason', {
    value: new Error('background failure'),
  })
  window.dispatchEvent(event)

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalled()
  })
  expect(fetchMock.mock.calls[0]?.[0]).toContain('/public/client-errors')
})
