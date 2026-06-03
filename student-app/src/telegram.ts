export type TelegramWebAppInitDataUnsafe = {
  query_id?: string
  user?: unknown
  receiver?: unknown
  chat?: unknown
  chat_type?: string
  chat_instance?: string
  start_param?: string
  auth_date?: number
  hash?: string
  signature?: string
}

export type TelegramWebApp = {
  initData: string
  initDataUnsafe?: TelegramWebAppInitDataUnsafe
  version?: string
  platform?: string
  colorScheme?: string
  isExpanded?: boolean
  viewportHeight?: number
  viewportStableHeight?: number
  themeParams?: Record<string, string>
  ready?: () => void
  expand?: () => void
  showScanQrPopup?: (
    params: { text?: string },
    onScan: (data: string) => boolean | void,
  ) => void
  closeScanQrPopup?: () => void
  openTelegramLink?: (url: string) => void
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp
    }
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null
}
