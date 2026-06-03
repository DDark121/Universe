import { describe, expect, it } from 'vitest'

import { extractQrToken } from './qr'

describe('extractQrToken', () => {
  it('strips a raw qr_ prefix', () => {
    expect(extractQrToken('qr_static_token')).toBe('static_token')
  })

  it('extracts a token from a telegram deeplink', () => {
    expect(extractQrToken('https://t.me/universe_bot?start=qr_static_token')).toBe('static_token')
  })

  it('extracts a token from tg:// deeplink formats', () => {
    expect(extractQrToken('tg://resolve?domain=universe_bot&start=qr_dynamic.jwt.token')).toBe(
      'dynamic.jwt.token',
    )
  })

  it('supports startapp deeplinks and leaves raw jwt tokens untouched', () => {
    expect(extractQrToken('https://t.me/universe_bot/app?startapp=qr_dynamic.jwt.token')).toBe(
      'dynamic.jwt.token',
    )
    expect(extractQrToken('dynamic.jwt.token')).toBe('dynamic.jwt.token')
  })
})
