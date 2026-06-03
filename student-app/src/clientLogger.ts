type ClientApp = 'student-app'
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

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const clientErrorsUrl = `${apiBaseUrl}/public/client-errors`
const sensitiveMarkers = ['token', 'secret', 'password', 'authorization', 'cookie', 'initdata', 'init_data', 'hash', 'signature']

let currentCorrelationId = ''
let globalHandlersInstalled = false

function createCorrelationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `student-${Date.now()}-${Math.random().toString(16).slice(2)}`
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

export function getCorrelationId() {
  if (!currentCorrelationId) {
    currentCorrelationId = createCorrelationId()
  }
  return currentCorrelationId
}

export function withCorrelationHeaders(headers?: HeadersInit) {
  const next = new Headers(headers)
  next.set('X-Correlation-ID', getCorrelationId())
  return next
}

export function captureCorrelationId(response: { headers?: Headers | null } | Response) {
  const nextId = response.headers?.get('X-Correlation-ID')
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
    app: 'student-app',
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
      headers: withCorrelationHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
      keepalive: true,
    })
  } catch {
    return
  }
}

export async function trackedFetch(
  url: string,
  init: RequestInit | undefined,
  context: Record<string, unknown>,
) {
  try {
    const response = await fetch(url, {
      ...init,
      headers: withCorrelationHeaders(init?.headers),
    })
    captureCorrelationId(response)
    if (response.status >= 500) {
      void reportClientError({
        message: `Unexpected HTTP ${response.status}`,
        context: {
          ...context,
          status: response.status,
          url,
          method: init?.method || 'GET',
        },
      })
    }
    return response
  } catch (error) {
    void reportClientError({
      message: error instanceof Error ? error.message : 'Network request failed',
      stack: error instanceof Error ? error.stack : undefined,
      context: {
        ...context,
        url,
        method: init?.method || 'GET',
      },
    })
    throw error
  }
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
