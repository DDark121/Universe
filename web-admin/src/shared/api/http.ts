import axios, { AxiosError } from 'axios'

import { getAccessToken } from '@/shared/auth/session'
import { captureCorrelationId, reportApiError, withCorrelationHeaders } from '@/shared/telemetry/clientLogger'

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export const api = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    'Content-Type': 'application/json',
  },
})

type AuthBridge = {
  refresh: () => Promise<void>
  onRefreshFail: () => void
}

let bridge: AuthBridge | null = null
let refreshPromise: Promise<void> | null = null

export function bindAuthBridge(payload: AuthBridge) {
  bridge = payload
}

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  config.headers = withCorrelationHeaders(config.headers)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    captureCorrelationId(response)
    return response
  },
  async (error: AxiosError) => {
    const request = error.config
    if (error.response) {
      captureCorrelationId(error.response)
    }
    if (!request) throw error

    const isAuthEndpoint = request.url?.includes('/auth/login') || request.url?.includes('/auth/refresh')
    const status = error.response?.status

    if (status === undefined || status >= 500) {
      reportApiError(error, {
        source: 'axios-response-interceptor',
      })
    }

    if (status !== 401 || isAuthEndpoint || !bridge) {
      throw error
    }

    if ((request as { _retry?: boolean })._retry) {
      bridge.onRefreshFail()
      throw error
    }

    ;(request as { _retry?: boolean })._retry = true

    if (!refreshPromise) {
      refreshPromise = bridge
        .refresh()
        .catch(() => {
          bridge?.onRefreshFail()
          throw error
        })
        .finally(() => {
          refreshPromise = null
        })
    }

    await refreshPromise
    return api(request)
  },
)
