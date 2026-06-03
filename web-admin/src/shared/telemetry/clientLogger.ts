import axios from 'axios'
import { AxiosHeaders, type AxiosError, type RawAxiosRequestHeaders } from 'axios'

type ClientApp = 'web-admin'
type ClientErrorLevel = 'error' | 'warning'

type ClientErrorPayload = {
  app: ClientApp
  level: ClientErrorLevel
  message: string
  stack?: string
  url: string
  user_agent: string
  correlation_id?: string
  release?: string
  context?: Record<string, unknown>
}

type ReportableError = Error | AxiosError | object

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'
const clientErrorsUrl = `${apiBaseUrl}/public/client-errors`
const sensitiveMarkers = ['token', 'secret', 'password', 'authorization', 'cookie', 'initdata', 'init_data', 'hash', 'signature']
const reportedErrors = new WeakSet<object>()

let currentCorrelationId = ''
let globalHandlersInstalled = false

function createCorrelationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `web-admin-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function sanitizeValue(value: unknown, depth = 4): unknown {
  if (depth <= 0) {
    return '[truncated]'
  }
  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      stack: value.stack?.slice(0, 4_000),
    }
  }
  if (Array.isArray(value)) {
    return value.map((entry) => sanitizeValue(entry, depth - 1))
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, entry]) => {
        const normalizedKey = key.toLowerCase()
        if (sensitiveMarkers.some((marker) => normalizedKey.includes(marker))) {
          return [key, '[redacted]']
        }
        return [key, sanitizeValue(entry, depth - 1)]
      }),
    )
  }
  if (typeof value === 'string' && value.length > 4_000) {
    return `${value.slice(0, 4_000)}...[truncated]`
  }
  return value
}

function currentUrl() {
  return typeof window !== 'undefined' ? window.location.href : 'unknown'
}

function currentUserAgent() {
  return typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown'
}

function markReported(error: unknown) {
  if (error && typeof error === 'object') {
    reportedErrors.add(error)
  }
}

function wasReported(error: unknown) {
  return Boolean(error && typeof error === 'object' && reportedErrors.has(error))
}

export function getCorrelationId() {
  if (!currentCorrelationId) {
    currentCorrelationId = createCorrelationId()
  }
  return currentCorrelationId
}

export function withCorrelationHeaders(
  headers?: AxiosHeaders | RawAxiosRequestHeaders | Record<string, unknown>,
) {
  const next = new AxiosHeaders()
  const source =
    headers && typeof headers === 'object' && 'toJSON' in headers && typeof headers.toJSON === 'function'
      ? headers.toJSON()
      : headers

  if (source && typeof source === 'object') {
    for (const [key, value] of Object.entries(source)) {
      if (value !== undefined && value !== null) {
        next.set(key, Array.isArray(value) ? value.map(String).join(', ') : String(value))
      }
    }
  }
  next.set('X-Correlation-ID', getCorrelationId())
  return next
}

export function captureCorrelationId(response: { headers?: unknown }) {
  let nextId: string | null | undefined
  if (response.headers instanceof Headers) {
    nextId = response.headers.get('X-Correlation-ID')
  } else if (response.headers && typeof response.headers === 'object') {
    const headerValue = (response.headers as Record<string, string | string[] | undefined>)['x-correlation-id']
    nextId = Array.isArray(headerValue) ? headerValue[0] : headerValue
  }
  if (nextId) {
    currentCorrelationId = nextId
  }
}

export async function reportClientError(input: {
  level?: ClientErrorLevel
  message: string
  stack?: string
  context?: Record<string, unknown>
}) {
  const payload: ClientErrorPayload = {
    app: 'web-admin',
    level: input.level || 'error',
    message: input.message.slice(0, 2_000),
    stack: input.stack?.slice(0, 8_000),
    url: currentUrl(),
    user_agent: currentUserAgent(),
    correlation_id: getCorrelationId(),
    release: import.meta.env.MODE,
    context: input.context ? (sanitizeValue(input.context) as Record<string, unknown>) : undefined,
  }

  try {
    await fetch(clientErrorsUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-ID': getCorrelationId(),
      },
      body: JSON.stringify(payload),
      keepalive: true,
    })
  } catch {
    return
  }
}

export function shouldReportApiError(error: unknown) {
  if (wasReported(error)) {
    return false
  }
  if (!axios.isAxiosError(error)) {
    return true
  }
  const status = error.response?.status
  return status === undefined || status >= 500
}

export function reportApiError(
  error: unknown,
  context: Record<string, unknown>,
  options?: { level?: ClientErrorLevel },
) {
  if (!shouldReportApiError(error)) {
    return
  }

  markReported(error)
  const axiosError = axios.isAxiosError(error) ? error : null
  const message =
    axiosError?.message ||
    (error instanceof Error ? error.message : typeof error === 'string' ? error : 'Unexpected client error')
  const stack = axiosError?.stack || (error instanceof Error ? error.stack : undefined)

  void reportClientError({
    level: options?.level || 'error',
    message,
    stack,
    context: {
      ...context,
      status: axiosError?.response?.status,
      method: axiosError?.config?.method?.toUpperCase(),
      url: axiosError?.config?.url,
    },
  })
}

export function installGlobalErrorHandlers() {
  if (globalHandlersInstalled || typeof window === 'undefined') {
    return
  }
  globalHandlersInstalled = true

  window.addEventListener('error', (event) => {
    void reportClientError({
      message: event.message || 'Unhandled window error',
      stack: event.error instanceof Error ? event.error.stack : undefined,
      context: {
        source: 'window.error',
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      },
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    void reportClientError({
      message: reason instanceof Error ? reason.message : 'Unhandled promise rejection',
      stack: reason instanceof Error ? reason.stack : undefined,
      context: {
        source: 'window.unhandledrejection',
        reason: sanitizeValue(reason),
      },
    })
  })
}

export function isErrorAlreadyReported(error: ReportableError) {
  return wasReported(error)
}
