const qrDeeplinkParamNames = ['start', 'startapp', 'startattach'] as const

function stripQrPrefix(value: string) {
  return value.startsWith('qr_') ? value.slice(3) : value
}

function deeplinkToken(value: string) {
  const candidates: string[] = []
  if (value.startsWith('?') && value.length > 1) {
    candidates.push(value.slice(1))
  }
  if (qrDeeplinkParamNames.some((key) => value.startsWith(`${key}=`))) {
    candidates.push(value)
  }

  const queryIndex = value.indexOf('?')
  if (queryIndex >= 0 && queryIndex < value.length - 1) {
    candidates.push(value.slice(queryIndex + 1))
  }

  try {
    const parsed = new URL(value.includes('://') ? value : `https://${value}`)
    if (parsed.search.length > 1) {
      candidates.push(parsed.search.slice(1))
    }
  } catch {
    // Ignore invalid URLs and fall back to raw token handling.
  }

  for (const query of candidates) {
    const params = new URLSearchParams(query)
    for (const key of qrDeeplinkParamNames) {
      const token = params.get(key)?.trim()
      if (token) {
        return token
      }
    }
  }

  return null
}

export function extractQrToken(rawValue: string) {
  const value = rawValue.trim()
  if (!value) {
    return ''
  }
  return stripQrPrefix(deeplinkToken(value) ?? value)
}
