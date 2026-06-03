import axios from 'axios'

export function getApiErrorMessage(error: unknown, fallback = 'Ошибка запроса') {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | {
          detail?: unknown
          error?: {
            message?: unknown
            details?: unknown
          }
        }
      | undefined
    const detail = data?.detail
    const wrappedMessage = data?.error?.message
    const wrappedDetails = data?.error?.details
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0]
      if (typeof first?.msg === 'string') return first.msg
    }
    if (typeof wrappedMessage === 'string' && wrappedMessage) return wrappedMessage
    if (typeof wrappedDetails === 'string' && wrappedDetails) return wrappedDetails
    if (typeof error.message === 'string' && error.message) return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}
