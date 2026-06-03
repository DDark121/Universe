import type { ApiMessage } from '@/shared/api/types'
import type { paths } from '@/shared/api/openapi.generated'
import { api } from '@/shared/api/http'

export type LoginPayload =
  paths['/api/v1/auth/login']['post']['requestBody']['content']['application/json']

export type TokenPairResponse =
  paths['/api/v1/auth/login']['post']['responses']['200']['content']['application/json']

export type MeResponse = {
  id: string
  username: string
  email: string | null
  phone_number: string | null
  full_name: string
  roles: string[]
  is_active: boolean
  must_change_password: boolean
}

export async function login(payload: LoginPayload) {
  const { data } = await api.post<TokenPairResponse>('/auth/login', payload)
  return data
}

export async function refresh(refreshToken: string) {
  const { data } = await api.post<TokenPairResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  })
  return data
}

export async function logout(refreshToken: string) {
  const { data } = await api.post<ApiMessage>('/auth/logout', {
    refresh_token: refreshToken,
  })
  return data
}

export async function me() {
  const { data } = await api.get<MeResponse>('/auth/me')
  return data
}

export async function changePassword(currentPassword: string, newPassword: string) {
  const { data } = await api.post<ApiMessage>('/auth/password/change', {
    current_password: currentPassword,
    new_password: newPassword,
  })
  return data
}

export async function setup2fa() {
  const { data } = await api.post<{ secret: string; provisioning_uri: string }>('/auth/2fa/setup')
  return data
}

export async function enable2fa(code: string) {
  const { data } = await api.post<ApiMessage>('/auth/2fa/enable', { code })
  return data
}

export async function disable2fa(code: string) {
  const { data } = await api.post<ApiMessage>('/auth/2fa/disable', { code })
  return data
}
