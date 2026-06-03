import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'

const { reportApiError, captureCorrelationId, withCorrelationHeaders } = vi.hoisted(() => ({
  reportApiError: vi.fn(),
  captureCorrelationId: vi.fn(),
  withCorrelationHeaders: vi.fn((headers?: AxiosHeaders) => {
    const next = headers instanceof AxiosHeaders ? headers : new AxiosHeaders(headers)
    next.set('X-Correlation-ID', 'test-correlation')
    return next
  }),
}))

vi.mock('@/shared/telemetry/clientLogger', () => ({
  reportApiError,
  captureCorrelationId,
  withCorrelationHeaders,
}))

vi.mock('@/shared/auth/session', () => ({
  getAccessToken: () => 'access-token',
}))

import { api } from '@/shared/api/http'

beforeEach(() => {
  reportApiError.mockClear()
  captureCorrelationId.mockClear()
  withCorrelationHeaders.mockClear()
})

it('adds correlation headers and reports unexpected axios failures', async () => {
  const adapter = async (config: InternalAxiosRequestConfig) => {
    throw new AxiosError(
      'Server failed',
      'ERR_BAD_RESPONSE',
      config,
      undefined,
      {
        status: 500,
        statusText: 'Server failed',
        headers: { 'x-correlation-id': 'backend-correlation' },
        config,
        data: {},
      },
    )
  }

  await expect(api.get('/students', { adapter })).rejects.toThrow('Server failed')

  expect(withCorrelationHeaders).toHaveBeenCalled()
  expect(reportApiError).toHaveBeenCalledWith(
    expect.any(AxiosError),
    expect.objectContaining({
      source: 'axios-response-interceptor',
    }),
  )
  expect(captureCorrelationId).toHaveBeenCalled()
})
