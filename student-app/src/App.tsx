import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import QRCode from 'react-qr-code'

import { reportClientError, trackedFetch } from './clientLogger'
import { extractQrToken } from './qr'
import { getTelegramWebApp, type TelegramWebApp } from './telegram'
import type {
  AbsenceReasonItem,
  AttendanceSummary,
  BootStatus,
  BootstrapResponse,
  FaqItem,
  HistoryItem,
  LinkedSession,
  RatingSnapshot,
  ScheduleItem,
  StudentProfile,
  TeacherAbsenceReasonItem,
  TeacherGroupItem,
  TeacherLessonAttendanceResponse,
  TeacherLessonItem,
  TeacherQrGenerateResponse,
  WarningItem,
} from './types'

const serviceBaseUrl = import.meta.env.VITE_TG_SERVICE_BASE_URL || '/tg'
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'

type TabKey =
  | 'home'
  | 'schedule'
  | 'qr'
  | 'history'
  | 'reasons'
  | 'faq'
  | 'teacher-lessons'
  | 'teacher-qr'
  | 'teacher-attendance'
  | 'teacher-reasons'
  | 'teacher-broadcast'

const studentTabs: Array<{ key: TabKey; label: string }> = [
  { key: 'home', label: 'Главная' },
  { key: 'schedule', label: 'Расписание' },
  { key: 'qr', label: 'QR' },
  { key: 'history', label: 'История' },
  { key: 'reasons', label: 'Причины' },
  { key: 'faq', label: 'FAQ / Профиль' },
]

const teacherTabs: Array<{ key: TabKey; label: string }> = [
  { key: 'home', label: 'Обзор' },
  { key: 'teacher-lessons', label: 'Занятия' },
  { key: 'teacher-qr', label: 'QR' },
  { key: 'teacher-attendance', label: 'Отметки' },
  { key: 'teacher-reasons', label: 'Причины' },
  { key: 'teacher-broadcast', label: 'Рассылки' },
]

const telegramInitRetries = 20
const telegramInitRetryDelayMs = 250
const pendingStatusPollMs = 10_000

type DebugEvent = {
  title: string
  timestamp: string
  data: unknown
}

type FaqAnswerBlock =
  | { type: 'paragraph'; content: string }
  | { type: 'list'; items: string[] }

function formatDateTime(value: string) {
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function buildDateRangeParams(daysBack = 30) {
  const dateTo = new Date()
  const dateFrom = new Date(dateTo)
  dateFrom.setDate(dateFrom.getDate() - daysBack)
  return new URLSearchParams({
    date_from: dateFrom.toISOString().slice(0, 10),
    date_to: dateTo.toISOString().slice(0, 10),
  })
}

function parseFaqAnswerBlocks(value: string): FaqAnswerBlock[] {
  const normalized = value.replace(/\r\n/g, '\n').trim()
  if (!normalized) {
    return []
  }

  return normalized
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const lines = block
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      const listItems = lines
        .map((line) => line.match(/^([-*•]|\d+[.)])\s+(.*)$/)?.[2]?.trim() || null)
        .filter((line): line is string => Boolean(line))

      if (lines.length > 0 && listItems.length === lines.length) {
        return { type: 'list', items: listItems }
      }

      return { type: 'paragraph', content: lines.join(' ') }
    })
}

function parseFaqKeywords(value: string) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function formatReasonType(value: string) {
  const labels: Record<string, string> = {
    illness: 'Болезнь',
    academic: 'Учебная деятельность',
    personal: 'Личная причина',
    other: 'Другое',
  }
  return labels[value] || value
}

function formatWarningReason(value: WarningItem['reason']) {
  if (!value) {
    return 'Причина не указана'
  }
  if (typeof value === 'string') {
    return value
  }
  return Object.entries(value)
    .map(([key, entry]) => `${key}: ${String(entry)}`)
    .join(', ')
}

function humanizeStatus(value?: string | null) {
  const labels: Record<string, string> = {
    planned: 'Запланировано',
    completed: 'Завершено',
    canceled: 'Отменено',
    rescheduled: 'Перенесено',
    present: 'Присутствовал',
    late: 'Опоздал',
    absent: 'Отсутствовал',
    pending: 'На проверке',
    accepted: 'Принято',
    approved: 'Принято',
    rejected: 'Отклонено',
    qr: 'QR',
    manual: 'Вручную',
    button: 'Кнопка',
  }
  return labels[value || ''] || value || 'Не отмечено'
}

function normalizeTelegramLink(value?: string | null) {
  const link = (value || '').trim()
  if (!link) {
    return ''
  }
  if (/^https?:\/\//i.test(link) || /^tg:\/\//i.test(link)) {
    return link
  }
  if (link.startsWith('t.me/')) {
    return `https://${link}`
  }
  return link
}

async function readError(response: Response) {
  try {
    const payload = (await response.json()) as unknown
    return formatApiError(payload) || 'Не удалось выполнить запрос'
  } catch {
    return 'Не удалось выполнить запрос'
  }
}

function formatApiErrorLocation(value: unknown) {
  if (!Array.isArray(value)) {
    return ''
  }
  const segments = value
    .map((segment) => String(segment).trim())
    .filter(Boolean)
  const structuralSegments = new Set(['body', 'query', 'path', 'header', 'cookie'])
  const filteredSegments = segments.filter((segment) => !structuralSegments.has(segment))
  return (filteredSegments.length > 0 ? filteredSegments : segments).join('.')
}

function formatApiErrorEntry(value: Record<string, unknown>) {
  const message =
    (typeof value.msg === 'string' && value.msg.trim()) ||
    (typeof value.message === 'string' && value.message.trim()) ||
    (typeof value.detail === 'string' && value.detail.trim()) ||
    ''
  const location = formatApiErrorLocation(value.loc)
  if (message) {
    return location ? `${location}: ${message}` : message
  }
  const parts = Object.entries(value)
    .map(([key, entry]) => {
      const formattedEntry = formatApiError(entry)
      if (!formattedEntry) {
        return null
      }
      return key === 'detail' || key === 'message' ? formattedEntry : `${key}: ${formattedEntry}`
    })
    .filter((entry): entry is string => Boolean(entry))
  return parts.join(', ')
}

function formatApiError(value: unknown): string | null {
  if (typeof value === 'string') {
    const normalized = value.trim()
    return normalized || null
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }

  if (Array.isArray(value)) {
    const parts = value
      .map((entry) => formatApiError(entry))
      .filter((entry): entry is string => Boolean(entry))
    return parts.length > 0 ? parts.join('; ') : null
  }

  if (value && typeof value === 'object') {
    return formatApiErrorEntry(value as Record<string, unknown>) || null
  }

  return null
}

function maskSecret(value: string) {
  if (value.length <= 16) {
    return value
  }
  return `${value.slice(0, 8)}...${value.slice(-4)}`
}

function sanitizeDebugValue(value: unknown): unknown {
  if (value instanceof Error) {
    return { name: value.name, message: value.message }
  }

  if (Array.isArray(value)) {
    return value.map((item) => sanitizeDebugValue(item))
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, entry]) => {
        const normalizedKey = key.toLowerCase()
        if (
          typeof entry === 'string' &&
          ['token', 'secret', 'initdata', 'init_data', 'authorization', 'hash', 'signature'].some((marker) =>
            normalizedKey.includes(marker),
          )
        ) {
          return [key, maskSecret(entry)]
        }
        return [key, sanitizeDebugValue(entry)]
      }),
    )
  }

  return value
}

function formatDebugValue(value: unknown) {
  return JSON.stringify(sanitizeDebugValue(value), null, 2)
}

function getTelegramSnapshot(webApp: TelegramWebApp | null) {
  return {
    telegramObjectPresent: typeof window !== 'undefined' ? Boolean(window.Telegram) : false,
    webAppPresent: Boolean(webApp),
    version: webApp?.version || null,
    platform: webApp?.platform || null,
    colorScheme: webApp?.colorScheme || null,
    isExpanded: webApp?.isExpanded ?? null,
    viewportHeight: webApp?.viewportHeight ?? null,
    viewportStableHeight: webApp?.viewportStableHeight ?? null,
    initDataLength: webApp?.initData?.length || 0,
    initData: webApp?.initData || '',
    initDataUnsafe: webApp?.initDataUnsafe || null,
    themeParams: webApp?.themeParams || null,
  }
}

export default function App() {
  const [bootStatus, setBootStatus] = useState<BootStatus>('loading')
  const [bootPayload, setBootPayload] = useState<BootstrapResponse | null>(null)
  const [session, setSession] = useState<LinkedSession | null>(null)
  const sessionRef = useRef<LinkedSession | null>(null)
  const initDataRef = useRef('')
  const [debugEvents, setDebugEvents] = useState<DebugEvent[]>([])
  const [statusRefreshBusy, setStatusRefreshBusy] = useState(false)
  const [statusRefreshError, setStatusRefreshError] = useState<string | null>(null)
  const [lastStatusCheckAt, setLastStatusCheckAt] = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<TabKey>('home')
  const [profile, setProfile] = useState<StudentProfile | null>(null)
  const [schedule, setSchedule] = useState<ScheduleItem[]>([])
  const [summary, setSummary] = useState<AttendanceSummary | null>(null)
  const [ratings, setRatings] = useState<RatingSnapshot[]>([])
  const [warnings, setWarnings] = useState<WarningItem[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [reasons, setReasons] = useState<AbsenceReasonItem[]>([])
  const [faqItems, setFaqItems] = useState<FaqItem[]>([])
  const [teacherLessons, setTeacherLessons] = useState<TeacherLessonItem[]>([])
  const [teacherGroups, setTeacherGroups] = useState<TeacherGroupItem[]>([])
  const [teacherReasons, setTeacherReasons] = useState<TeacherAbsenceReasonItem[]>([])
  const [teacherAttendance, setTeacherAttendance] = useState<TeacherLessonAttendanceResponse | null>(null)
  const [teacherQr, setTeacherQr] = useState<TeacherQrGenerateResponse | null>(null)
  const [selectedTeacherLessonId, setSelectedTeacherLessonId] = useState('')

  const [globalError, setGlobalError] = useState<string | null>(null)
  const [homeLoading, setHomeLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [faqLoading, setFaqLoading] = useState(false)
  const [teacherLoading, setTeacherLoading] = useState(false)

  const [fullName, setFullName] = useState('')
  const [groupCode, setGroupCode] = useState('')
  const [note, setNote] = useState('')
  const [onboardingError, setOnboardingError] = useState<string | null>(null)
  const [onboardingBusy, setOnboardingBusy] = useState(false)

  const [qrInput, setQrInput] = useState('')
  const [qrBusy, setQrBusy] = useState(false)
  const [qrMessage, setQrMessage] = useState<string | null>(null)

  const [reasonLessonId, setReasonLessonId] = useState('')
  const [reasonType, setReasonType] = useState('illness')
  const [reasonComment, setReasonComment] = useState('')
  const [reasonPredeclared, setReasonPredeclared] = useState(false)
  const [reasonFile, setReasonFile] = useState<File | null>(null)
  const [reasonBusy, setReasonBusy] = useState(false)
  const [reasonMessage, setReasonMessage] = useState<string | null>(null)

  const [faqQuery, setFaqQuery] = useState('')
  const [faqCategoryId, setFaqCategoryId] = useState('')
  const [debugOpen, setDebugOpen] = useState(false)
  const [teacherQrBusy, setTeacherQrBusy] = useState(false)
  const [teacherAttendanceBusy, setTeacherAttendanceBusy] = useState(false)
  const [teacherReasonBusy, setTeacherReasonBusy] = useState<string | null>(null)
  const [teacherBroadcastBusy, setTeacherBroadcastBusy] = useState(false)
  const [teacherBroadcastGroupId, setTeacherBroadcastGroupId] = useState('')
  const [teacherBroadcastMessage, setTeacherBroadcastMessage] = useState('')
  const [teacherMessage, setTeacherMessage] = useState<string | null>(null)
  const [teacherStatusDrafts, setTeacherStatusDrafts] = useState<Record<string, 'present' | 'late' | 'absent'>>({})
  const [teacherCorrectionDrafts, setTeacherCorrectionDrafts] = useState<Record<string, string>>({})
  const [teacherModerationDrafts, setTeacherModerationDrafts] = useState<Record<string, string>>({})

  const appendDebugEvent = useCallback((title: string, data: unknown) => {
    setDebugEvents((current) => [
      ...current,
      {
        title,
        timestamp: new Date().toISOString(),
        data: sanitizeDebugValue(data),
      },
    ])
  }, [])

  useEffect(() => {
    sessionRef.current = session
  }, [session])

  const requestBootstrap = useCallback(async (initData: string, fallbackMessage?: string) => {
    const url = `${serviceBaseUrl}/webapp/bootstrap`
    appendDebugEvent('bootstrap-request', {
      url,
      method: 'POST',
      initData,
    })
    const response = await trackedFetch(
      url,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
      },
      {
        feature: 'bootstrap',
      },
    )
    if (!response.ok) {
      const detail = await readError(response)
      appendDebugEvent('bootstrap-response', {
        url,
        status: response.status,
        ok: response.ok,
        detail,
      })
      throw new Error(detail)
    }
    const payload = (await response.json()) as BootstrapResponse
    const nextPayload =
      fallbackMessage && payload.status !== 'linked' && !payload.message ? { ...payload, message: fallbackMessage } : payload
    appendDebugEvent('bootstrap-response', {
      url,
      status: response.status,
      ok: response.ok,
      payload: nextPayload,
    })
    return nextPayload
  }, [appendDebugEvent])

  const refreshSession = useCallback(async (activeSession: LinkedSession): Promise<LinkedSession> => {
    const url = `${apiBaseUrl}/auth/refresh`
    appendDebugEvent('refresh-request', {
      url,
      method: 'POST',
    })
    const response = await trackedFetch(
      url,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: activeSession.refreshToken }),
      },
      {
        feature: 'auth-refresh',
      },
    )
    if (!response.ok) {
      const detail = await readError(response)
      appendDebugEvent('refresh-response', {
        url,
        status: response.status,
        ok: response.ok,
        detail,
      })
      throw new Error(detail)
    }
    const payload = (await response.json()) as {
      access_token: string
      refresh_token: string
    }
    appendDebugEvent('refresh-response', {
      url,
      status: response.status,
      ok: response.ok,
      payload,
    })
    const nextSession = {
      ...activeSession,
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
    }
    sessionRef.current = nextSession
    setSession(nextSession)
    return nextSession
  }, [appendDebugEvent])

  const authorizedRequest = useCallback(async (path: string, init?: RequestInit) => {
    const currentSession = sessionRef.current
    if (!currentSession) {
      throw new Error('Сессия отсутствует')
    }

    const request = async (token: string) => {
      const headers = new Headers(init?.headers)
      headers.set('Authorization', `Bearer ${token}`)
      const url = `${apiBaseUrl}${path}`
      appendDebugEvent('api-request', {
        url,
        path,
        method: init?.method || 'GET',
        hasBody: Boolean(init?.body),
        bodyType: init?.body instanceof FormData ? 'FormData' : typeof init?.body,
      })
      return trackedFetch(
        url,
        {
          ...init,
          headers,
        },
        {
          feature: 'authorized-request',
          path,
        },
      )
    }

    let response = await request(currentSession.accessToken)
    if (response.status === 401) {
      appendDebugEvent('api-response', {
        path,
        status: response.status,
        ok: response.ok,
        detail: 'Unauthorized, trying refresh',
      })
      const refreshed = await refreshSession(currentSession)
      response = await request(refreshed.accessToken)
    }
    if (!response.ok) {
      const detail = await readError(response)
      appendDebugEvent('api-response', {
        path,
        status: response.status,
        ok: response.ok,
        detail,
      })
      throw new Error(detail)
    }
    if (response.status === 204) {
      appendDebugEvent('api-response', {
        path,
        status: response.status,
        ok: response.ok,
        payload: null,
      })
      return null
    }
    const payload = await response.json()
    appendDebugEvent('api-response', {
      path,
      status: response.status,
      ok: response.ok,
      payload,
    })
    return payload
  }, [appendDebugEvent, refreshSession])

  const loadInitialData = useCallback(async (activeSession: LinkedSession) => {
    setHomeLoading(true)
    try {
      sessionRef.current = activeSession
      const summaryParams = buildDateRangeParams()
      const [profilePayload, schedulePayload, summaryPayload, ratingPayload, warningsPayload, reasonsPayload, faqPayload] =
        await Promise.all([
          authorizedRequest('/student/profile'),
          authorizedRequest('/student/schedule'),
          authorizedRequest(`/student/attendance/summary?${summaryParams.toString()}`),
          authorizedRequest('/student/rating'),
          authorizedRequest('/student/warnings'),
          authorizedRequest('/student/absence-reasons'),
          authorizedRequest('/student/faq'),
        ])
      setProfile(profilePayload as StudentProfile)
      setSchedule((schedulePayload as ScheduleItem[]) || [])
      setSummary((summaryPayload as AttendanceSummary) || null)
      setRatings((ratingPayload as RatingSnapshot[]) || [])
      setWarnings((warningsPayload as WarningItem[]) || [])
      setReasons((reasonsPayload as AbsenceReasonItem[]) || [])
      setFaqItems((faqPayload as FaqItem[]) || [])
      setGlobalError(null)
    } catch (error) {
      void reportClientError({
        message: error instanceof Error ? error.message : 'Student initial data load failed',
        stack: error instanceof Error ? error.stack : undefined,
        context: {
          feature: 'load-initial-data',
        },
      })
      setGlobalError(error instanceof Error ? error.message : 'Не удалось загрузить данные студента')
    } finally {
      setHomeLoading(false)
    }
  }, [authorizedRequest])

  const loadTeacherData = useCallback(async (activeSession: LinkedSession) => {
    setTeacherLoading(true)
    try {
      sessionRef.current = activeSession
      const [lessonsPayload, groupsPayload, reasonsPayload] = await Promise.all([
        authorizedRequest('/teacher/lessons'),
        authorizedRequest('/teacher/groups'),
        authorizedRequest('/teacher/absence-reasons'),
      ])
      const lessons = (lessonsPayload as TeacherLessonItem[]) || []
      setTeacherLessons(lessons)
      setTeacherGroups((groupsPayload as TeacherGroupItem[]) || [])
      setTeacherReasons((reasonsPayload as TeacherAbsenceReasonItem[]) || [])
      setSelectedTeacherLessonId((current) => current || lessons[0]?.id || '')
      setGlobalError(null)
    } catch (error) {
      void reportClientError({
        message: error instanceof Error ? error.message : 'Teacher initial data load failed',
        stack: error instanceof Error ? error.stack : undefined,
        context: {
          feature: 'load-teacher-data',
        },
      })
      setGlobalError(error instanceof Error ? error.message : 'Не удалось загрузить данные преподавателя')
    } finally {
      setTeacherLoading(false)
    }
  }, [authorizedRequest])

  const applyBootstrapPayload = useCallback(async (payload: BootstrapResponse) => {
    setBootPayload(payload)
    setBootStatus(payload.status)
    setLastStatusCheckAt(new Date().toISOString())
    setStatusRefreshError(null)
    if (payload.status === 'linked' && payload.user && payload.tokens) {
      const nextSession: LinkedSession = {
        accessToken: payload.tokens.access_token,
        refreshToken: payload.tokens.refresh_token,
        user: payload.user,
      }
      setSession(nextSession)
      setProfile({
        id: payload.user.id,
        username: payload.user.username,
        full_name: payload.user.full_name,
        email: payload.user.email,
        phone_number: payload.user.phone_number,
      })
      if (payload.user.roles.includes('teacher') && !payload.user.roles.includes('student')) {
        setActiveTab('home')
        setSchedule([])
        setSummary(null)
        setRatings([])
        setWarnings([])
        setReasons([])
        setFaqItems([])
        await loadTeacherData(nextSession)
      } else {
        setTeacherLessons([])
        setTeacherGroups([])
        setTeacherReasons([])
        setTeacherAttendance(null)
        setTeacherQr(null)
        await loadInitialData(nextSession)
      }
      return
    }
    sessionRef.current = null
    setSession(null)
    setProfile(null)
    setSummary(null)
    setRatings([])
    setWarnings([])
    setTeacherLessons([])
    setTeacherGroups([])
    setTeacherReasons([])
    setTeacherAttendance(null)
    setTeacherQr(null)
  }, [loadInitialData, loadTeacherData])

  const boot = useCallback(async (initData: string, fallbackMessage?: string) => {
    setBootStatus('loading')
    setGlobalError(null)
    setStatusRefreshError(null)
    try {
      const payload = await requestBootstrap(initData, fallbackMessage)
      await applyBootstrapPayload(payload)
    } catch (error) {
      void reportClientError({
        message: error instanceof Error ? error.message : 'Mini app bootstrap failed',
        stack: error instanceof Error ? error.stack : undefined,
        context: {
          feature: 'bootstrap',
        },
      })
      appendDebugEvent('bootstrap-error', {
        message: error instanceof Error ? error.message : 'Не удалось открыть мини-приложение',
        error,
      })
      setBootStatus('error')
      setGlobalError(error instanceof Error ? error.message : 'Не удалось открыть мини-приложение')
    }
  }, [appendDebugEvent, applyBootstrapPayload, requestBootstrap])

  const loadHistory = useCallback(async (force = false) => {
    if (activeTab !== 'history' || !sessionRef.current || (!force && history.length > 0)) {
      return
    }
    setHistoryLoading(true)
    try {
      const params = buildDateRangeParams()
      const payload = await authorizedRequest(`/student/attendance/history?${params.toString()}`)
      setHistory((payload as HistoryItem[]) || [])
      setGlobalError(null)
    } catch (error) {
      void reportClientError({
        level: 'warning',
        message: error instanceof Error ? error.message : 'History load failed',
        stack: error instanceof Error ? error.stack : undefined,
        context: {
          feature: 'history',
        },
      })
      setGlobalError(error instanceof Error ? error.message : 'Не удалось загрузить историю')
    } finally {
      setHistoryLoading(false)
    }
  }, [activeTab, authorizedRequest, history.length])

  const refreshBindingStatus = useCallback(async (reason: 'manual' | 'poll' = 'manual') => {
    if (!initDataRef.current || statusRefreshBusy) {
      return
    }
    setStatusRefreshBusy(true)
    setStatusRefreshError(null)
    appendDebugEvent('status-refresh-request', {
      reason,
      currentStatus: bootStatus,
      lastStatusCheckAt,
    })
    try {
      const payload = await requestBootstrap(initDataRef.current)
      await applyBootstrapPayload(payload)
      appendDebugEvent('status-refresh-response', {
        reason,
        nextStatus: payload.status,
        resolvedAt: payload.resolved_at || null,
      })
    } catch (error) {
      void reportClientError({
        level: 'warning',
        message: error instanceof Error ? error.message : 'Binding status refresh failed',
        stack: error instanceof Error ? error.stack : undefined,
        context: {
          feature: 'binding-status-refresh',
          reason,
        },
      })
      appendDebugEvent('status-refresh-error', {
        reason,
        message: error instanceof Error ? error.message : 'Не удалось обновить статус заявки',
        error,
      })
      setStatusRefreshError(error instanceof Error ? error.message : 'Не удалось обновить статус заявки')
    } finally {
      setStatusRefreshBusy(false)
    }
  }, [appendDebugEvent, applyBootstrapPayload, bootStatus, lastStatusCheckAt, requestBootstrap, statusRefreshBusy])

  useEffect(() => {
    let cancelled = false

    async function bootstrapTelegramSession() {
      appendDebugEvent('app-init', {
        serviceBaseUrl,
        apiBaseUrl,
        locationHref: window.location.href,
        userAgent: navigator.userAgent,
        telegram: getTelegramSnapshot(getTelegramWebApp()),
      })

      for (let attempt = 0; attempt < telegramInitRetries; attempt += 1) {
        const webApp = getTelegramWebApp()
        webApp?.ready?.()
        webApp?.expand?.()

        const initData = webApp?.initData || ''
        appendDebugEvent('telegram-probe', {
          attempt: attempt + 1,
          maxAttempts: telegramInitRetries,
          retryDelayMs: telegramInitRetryDelayMs,
          telegram: getTelegramSnapshot(webApp),
        })

        if (initData) {
          initDataRef.current = initData
          appendDebugEvent('telegram-init-data', {
            attempt: attempt + 1,
            telegram: getTelegramSnapshot(webApp),
          })
          if (!cancelled) {
            await boot(initData)
          }
          return
        }

        await new Promise((resolve) => {
          window.setTimeout(resolve, telegramInitRetryDelayMs)
        })
      }

      if (!cancelled) {
        appendDebugEvent('telegram-init-timeout', {
          attempts: telegramInitRetries,
          retryDelayMs: telegramInitRetryDelayMs,
          telegram: getTelegramSnapshot(getTelegramWebApp()),
        })
        setBootStatus('error')
        setGlobalError('Telegram не передал initData. Откройте mini app из кнопки бота и попробуйте снова.')
      }
    }

    void bootstrapTelegramSession()

    return () => {
      cancelled = true
    }
  }, [appendDebugEvent, boot])

  useEffect(() => {
    if (bootPayload?.requested_full_name) {
      setFullName(bootPayload.requested_full_name)
    }
    if (bootPayload?.group_code) {
      setGroupCode(bootPayload.group_code)
    }
    if (bootPayload?.note) {
      setNote(bootPayload.note)
    }
  }, [bootPayload])

  useEffect(() => {
    if (bootStatus === 'linked' && session) {
      void loadHistory()
    }
  }, [bootStatus, loadHistory, session])

  useEffect(() => {
    if (bootStatus !== 'pending') {
      return
    }
    const intervalId = window.setInterval(() => {
      void refreshBindingStatus('poll')
    }, pendingStatusPollMs)
    return () => {
      window.clearInterval(intervalId)
    }
  }, [bootStatus, refreshBindingStatus])

  async function searchFaq(query = faqQuery, categoryId = faqCategoryId) {
    setFaqLoading(true)
    try {
      const params = new URLSearchParams()
      if (query.trim()) {
        params.set('query', query.trim())
      }
      if (categoryId) {
        params.set('category_id', categoryId)
      }
      const payload = await authorizedRequest(`/student/faq${params.toString() ? `?${params.toString()}` : ''}`)
      setFaqItems((payload as FaqItem[]) || [])
      setGlobalError(null)
    } catch (error) {
      void reportClientError({
        level: 'warning',
        message: error instanceof Error ? error.message : 'FAQ search failed',
        stack: error instanceof Error ? error.stack : undefined,
        context: {
          feature: 'faq-search',
          query,
          categoryId,
        },
      })
      setGlobalError(error instanceof Error ? error.message : 'Не удалось загрузить FAQ')
    } finally {
      setFaqLoading(false)
    }
  }

  async function submitBindingRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOnboardingError(null)
    if (!fullName.trim()) {
      setOnboardingError('Введите полное имя для заявки.')
      return
    }
    setOnboardingBusy(true)
    try {
      const url = `${serviceBaseUrl}/webapp/binding-request`
      const requestPayload = {
        init_data: initDataRef.current,
        full_name: fullName.trim(),
        group_code: groupCode.trim() || null,
        note: note.trim() || null,
      }
      appendDebugEvent('binding-request-request', {
        url,
        method: 'POST',
        payload: requestPayload,
      })
      const response = await trackedFetch(
        url,
        {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestPayload),
        },
        {
          feature: 'binding-request',
        },
      )
      if (!response.ok) {
        const detail = await readError(response)
        appendDebugEvent('binding-request-response', {
          url,
          status: response.status,
          ok: response.ok,
          detail,
        })
        throw new Error(detail)
      }
      const payload = (await response.json()) as BootstrapResponse
      appendDebugEvent('binding-request-response', {
        url,
        status: response.status,
        ok: response.ok,
        payload,
      })
      await boot(initDataRef.current, payload.message || 'Заявка отправлена')
    } catch (error) {
      appendDebugEvent('binding-request-error', {
        message: error instanceof Error ? error.message : 'Не удалось отправить заявку',
        error,
      })
      setOnboardingError(error instanceof Error ? error.message : 'Не удалось отправить заявку')
    } finally {
      setOnboardingBusy(false)
    }
  }

  async function submitQrToken(rawToken: string) {
    const qrToken = extractQrToken(rawToken)
    if (!qrToken) {
      setQrMessage('Не удалось распознать QR токен.')
      return
    }

    setQrBusy(true)
    setQrMessage(null)
    try {
      const payload = (await authorizedRequest('/student/attendance/mark-qr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qr_token: qrToken }),
      })) as { status: string }
      setQrInput('')
      setQrMessage(`Посещаемость отмечена: ${payload.status}.`)
      setHistory([])
      await loadInitialData(sessionRef.current as LinkedSession)
    } catch (error) {
      setQrMessage(error instanceof Error ? error.message : 'Не удалось отметить посещаемость')
    } finally {
      setQrBusy(false)
    }
  }

  function scanQrWithTelegram() {
    const webApp = getTelegramWebApp()
    if (!webApp?.showScanQrPopup) {
      setQrMessage('Сканер Telegram недоступен. Вставьте токен вручную.')
      return
    }
    webApp.showScanQrPopup({ text: 'Наведите камеру на QR преподавателя' }, (value) => {
      if (!value) {
        return false
      }
      void submitQrToken(value)
      webApp.closeScanQrPopup?.()
      return true
    })
  }

  async function submitAbsenceReason(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setReasonMessage(null)
    if (!reasonLessonId) {
      setReasonMessage('Выберите занятие.')
      return
    }
    if (!reasonType) {
      setReasonMessage('Выберите тип причины.')
      return
    }

    setReasonBusy(true)
    try {
      const formData = new FormData()
      formData.append('lesson_id', reasonLessonId)
      formData.append('reason_type', reasonType)
      formData.append('comment', reasonComment)
      formData.append('is_predeclared', String(reasonPredeclared))
      if (reasonFile) {
        formData.append('file', reasonFile)
      }
      await authorizedRequest('/student/absence-reasons', {
        method: 'POST',
        body: formData,
      })
      setReasonLessonId('')
      setReasonComment('')
      setReasonPredeclared(false)
      setReasonFile(null)
      setReasonMessage(
        reasonPredeclared ? 'Предварительная причина отсутствия отправлена.' : 'Причина отсутствия отправлена.',
      )
      const payload = await authorizedRequest('/student/absence-reasons')
      setReasons((payload as AbsenceReasonItem[]) || [])
    } catch (error) {
      setReasonMessage(error instanceof Error ? error.message : 'Не удалось отправить причину')
    } finally {
      setReasonBusy(false)
    }
  }

  const nextLesson = useMemo(() => {
    const now = Date.now()
    return schedule.find((item) => new Date(item.ends_at).getTime() >= now) || schedule[0] || null
  }, [schedule])

  const userRoles = session?.user.roles || bootPayload?.user?.roles || []
  const isTeacherMode = userRoles.includes('teacher') && !userRoles.includes('student')
  const activeTabs = isTeacherMode ? teacherTabs : studentTabs
  const nextTeacherLesson = useMemo(() => {
    const now = Date.now()
    return teacherLessons.find((item) => new Date(item.ends_at).getTime() >= now) || teacherLessons[0] || null
  }, [teacherLessons])
  const selectedTeacherLesson =
    teacherLessons.find((item) => item.id === selectedTeacherLessonId) || nextTeacherLesson || teacherLessons[0] || null
  const pendingTeacherReasons = teacherReasons.filter((item) => item.status === 'pending')
  const teacherAttendanceMarked = teacherAttendance?.students.filter((item) => Boolean(item.status)).length ?? 0
  const teacherAttendanceTotal = teacherAttendance?.students.length ?? 0
  const latestRating = ratings[0] || null
  const activeGroupLabel = nextLesson?.group_name || schedule[0]?.group_name || bootPayload?.group_code || 'Группа не указана'
  const teacherGroupLabel = selectedTeacherLesson?.group_name || teacherGroups[0]?.name || 'Группа не выбрана'
  const totalTrackedEvents = (summary?.present ?? 0) + (summary?.late ?? 0) + (summary?.absent ?? 0)
  const attendanceCoverage =
    totalTrackedEvents === 0 ? 0 : Math.round((((summary?.present ?? 0) + (summary?.late ?? 0)) / totalTrackedEvents) * 100)
  const punctualityRate =
    (summary?.present ?? 0) + (summary?.late ?? 0) === 0
      ? 0
      : Math.round(((summary?.present ?? 0) / ((summary?.present ?? 0) + (summary?.late ?? 0))) * 100)
  const riskStatusLabel = warnings.length > 0 ? 'Нужен контроль' : 'Стабильно'
  const debugEnabled =
    import.meta.env.DEV ||
    (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('debug'))

  const faqCategories = useMemo(
    () =>
      Array.from(new Map(faqItems.map((item) => [item.category_id, item.category_name])).entries()).map(([id, name]) => ({
        id,
        name,
      })),
    [faqItems],
  )

  function startPredeclaredReason(lessonId: string) {
    setReasonLessonId(lessonId)
    setReasonPredeclared(true)
    setReasonMessage('Режим предварительного заявления включен для выбранного занятия.')
    setActiveTab('reasons')
  }

  async function loadTeacherAttendance(lessonId = selectedTeacherLessonId) {
    if (!lessonId) {
      setTeacherMessage('Выберите занятие.')
      return
    }
    setTeacherAttendanceBusy(true)
    setTeacherMessage(null)
    try {
      const payload = await authorizedRequest(`/teacher/lessons/${encodeURIComponent(lessonId)}/attendance`)
      setTeacherAttendance(payload as TeacherLessonAttendanceResponse)
      setSelectedTeacherLessonId(lessonId)
      setActiveTab('teacher-attendance')
    } catch (error) {
      setTeacherMessage(error instanceof Error ? error.message : 'Не удалось загрузить отметки')
    } finally {
      setTeacherAttendanceBusy(false)
    }
  }

  async function generateTeacherQr(lessonId = selectedTeacherLessonId) {
    if (!lessonId) {
      setTeacherMessage('Выберите занятие для QR.')
      return
    }
    setTeacherQrBusy(true)
    setTeacherMessage(null)
    try {
      const payload = await authorizedRequest('/teacher/qr/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lesson_id: lessonId }),
      })
      setTeacherQr(payload as TeacherQrGenerateResponse)
      setSelectedTeacherLessonId(lessonId)
      setActiveTab('teacher-qr')
    } catch (error) {
      setTeacherMessage(error instanceof Error ? error.message : 'Не удалось сгенерировать QR')
    } finally {
      setTeacherQrBusy(false)
    }
  }

  async function correctTeacherAttendance(studentId: string) {
    if (!teacherAttendance?.lesson.id) {
      setTeacherMessage('Сначала откройте занятие.')
      return
    }
    const statusValue = teacherStatusDrafts[studentId] || teacherAttendance.students.find((item) => item.student_id === studentId)?.status
    const reason = (teacherCorrectionDrafts[studentId] || '').trim()
    if (!statusValue) {
      setTeacherMessage('Выберите статус отметки.')
      return
    }
    if (!reason) {
      setTeacherMessage('Укажите причину корректировки.')
      return
    }
    setTeacherAttendanceBusy(true)
    setTeacherMessage(null)
    try {
      await authorizedRequest('/teacher/attendance/correct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lesson_id: teacherAttendance.lesson.id,
          student_id: studentId,
          status: statusValue,
          reason,
        }),
      })
      setTeacherCorrectionDrafts((current) => ({ ...current, [studentId]: '' }))
      setTeacherStatusDrafts((current) => {
        const next = { ...current }
        delete next[studentId]
        return next
      })
      setTeacherMessage('Отметка сохранена.')
      await loadTeacherAttendance(teacherAttendance.lesson.id)
    } catch (error) {
      setTeacherMessage(error instanceof Error ? error.message : 'Не удалось сохранить отметку')
    } finally {
      setTeacherAttendanceBusy(false)
    }
  }

  async function moderateTeacherReason(reasonId: string, statusValue: 'accepted' | 'rejected') {
    setTeacherReasonBusy(reasonId)
    setTeacherMessage(null)
    try {
      await authorizedRequest('/teacher/absence-reasons/moderate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reason_id: reasonId,
          status: statusValue,
          comment: teacherModerationDrafts[reasonId] || undefined,
        }),
      })
      const payload = await authorizedRequest('/teacher/absence-reasons')
      setTeacherReasons((payload as TeacherAbsenceReasonItem[]) || [])
      setTeacherMessage(statusValue === 'accepted' ? 'Причина принята.' : 'Причина отклонена.')
    } catch (error) {
      setTeacherMessage(error instanceof Error ? error.message : 'Не удалось сохранить решение')
    } finally {
      setTeacherReasonBusy(null)
    }
  }

  async function sendTeacherBroadcast(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!teacherBroadcastGroupId) {
      setTeacherMessage('Выберите группу.')
      return
    }
    if (!teacherBroadcastMessage.trim()) {
      setTeacherMessage('Введите сообщение.')
      return
    }
    setTeacherBroadcastBusy(true)
    setTeacherMessage(null)
    try {
      const params = new URLSearchParams({
        group_id: teacherBroadcastGroupId,
        message: teacherBroadcastMessage.trim(),
      })
      const payload = (await authorizedRequest(`/teacher/broadcasts?${params.toString()}`, {
        method: 'POST',
      })) as { recipients?: number }
      setTeacherBroadcastMessage('')
      setTeacherMessage(`Рассылка поставлена в очередь. Получателей: ${payload.recipients ?? 0}.`)
    } catch (error) {
      setTeacherMessage(error instanceof Error ? error.message : 'Не удалось отправить рассылку')
    } finally {
      setTeacherBroadcastBusy(false)
    }
  }

  function openTeacherQrLink() {
    const link = normalizeTelegramLink(teacherQr?.deeplink)
    if (!link) {
      return
    }
    const webApp = getTelegramWebApp()
    if (webApp?.openTelegramLink) {
      webApp.openTelegramLink(link)
      return
    }
    window.open(link, '_blank', 'noopener,noreferrer')
  }

  useEffect(() => {
    if (bootStatus === 'error') {
      setDebugOpen(true)
    }
  }, [bootStatus])

  const debugPanel = bootStatus !== 'linked' || (debugEnabled && debugOpen) ? <DebugPanel events={debugEvents} /> : null

  if (bootStatus === 'loading') {
    return (
      <Splash title="Подключаем студенческий кабинет" subtitle="Проверяем Telegram-сессию и загружаем данные.">
        {debugPanel}
      </Splash>
    )
  }

  if (bootStatus === 'error') {
    return (
      <Splash title="Не удалось открыть mini app" subtitle={globalError || 'Попробуйте открыть приложение заново из Telegram.'}>
        {debugPanel}
      </Splash>
    )
  }

  if (bootStatus === 'link_required' || bootStatus === 'rejected') {
    return (
      <OnboardingLayout
        title={bootStatus === 'rejected' ? 'Заявка отклонена' : 'Создание доступа'}
        subtitle={
          bootStatus === 'rejected'
            ? bootPayload?.message || 'Проверьте данные и отправьте заявку повторно.'
            : 'Отправьте заявку на привязку Telegram к вашей студенческой записи.'
        }
      >
        <div className="onboarding-stack">
          <form className="panel panel-form" onSubmit={submitBindingRequest}>
            <label>
              <span>ФИО</span>
              <input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Иванов Иван" />
            </label>
            <label>
              <span>Код группы</span>
              <input value={groupCode} onChange={(event) => setGroupCode(event.target.value)} placeholder="SE-101" />
            </label>
            <label>
              <span>Комментарий</span>
              <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={4} placeholder="Например: переведен недавно, нужна проверка группы." />
            </label>
            {onboardingError ? <p className="message error">{onboardingError}</p> : null}
            <button className="primary-button" type="submit" disabled={onboardingBusy}>
              {onboardingBusy ? 'Отправляем...' : 'Отправить заявку'}
            </button>
          </form>

          <section className="panel">
            <div className="section-head">
              <h2>Что подготовить</h2>
              <span className="pill accepted">3 шага</span>
            </div>
            <div className="checklist">
              <article className="checklist-item">
                <strong>Полное имя без сокращений</strong>
                <p>Так администратор быстрее найдет запись студента и не отклонит заявку из-за расхождения данных.</p>
              </article>
              <article className="checklist-item">
                <strong>Добавьте код группы</strong>
                <p>Если группа уже известна, привязка обычно проходит заметно быстрее и без уточняющих сообщений.</p>
              </article>
              <article className="checklist-item">
                <strong>Оставьте комментарий при нестандартной ситуации</strong>
                <p>Например, если вы недавно перевелись, восстановились или еще не видите расписание.</p>
              </article>
            </div>
          </section>
        </div>
        {debugPanel}
      </OnboardingLayout>
    )
  }

  if (bootStatus === 'pending') {
    return (
      <OnboardingLayout
        title="Заявка отправлена"
        subtitle={bootPayload?.message || 'Администратор проверит ваши данные и одобрит доступ.'}
      >
        <div className="onboarding-stack">
          <div className="panel">
            <div className="section-head">
              <div>
                <h2 style={{ margin: 0 }}>Статус заявки</h2>
                <p className="muted" style={{ margin: '6px 0 0' }}>
                  Обновляем автоматически каждые 10 секунд. После одобрения кабинет откроется автоматически.
                </p>
              </div>
              <button type="button" onClick={() => void refreshBindingStatus('manual')} disabled={statusRefreshBusy}>
                {statusRefreshBusy ? 'Проверяем...' : 'Проверить статус'}
              </button>
            </div>

            <div className="status-grid">
              <StatusTile label="Текущий статус" value={<span className="pill pending">pending</span>} />
              <StatusTile label="Telegram" value={bootPayload?.telegram_username || 'username не указан'} />
              <StatusTile label="ФИО" value={bootPayload?.requested_full_name || fullName || 'Не указано'} />
              <StatusTile label="Группа" value={bootPayload?.group_code || 'Не указана'} />
              <StatusTile label="Комментарий" value={bootPayload?.note || 'Нет комментария'} />
              <StatusTile label="Последняя проверка" value={lastStatusCheckAt ? formatDateTime(lastStatusCheckAt) : 'Только что'} />
            </div>

            {statusRefreshError ? <p className="message error">{statusRefreshError}</p> : null}
          </div>

          <section className="panel">
            <div className="section-head">
              <h2>Что происходит дальше</h2>
              <span className="pill accepted">Auto-refresh</span>
            </div>
            <div className="checklist">
              <article className="checklist-item">
                <strong>Заявка уже в очереди</strong>
                <p>Администратор проверит ФИО, группу и связь с вашей студенческой записью.</p>
              </article>
              <article className="checklist-item">
                <strong>После одобрения кабинет откроется сам</strong>
                <p>Ничего дополнительно переустанавливать не нужно. Достаточно оставить mini app открытым или зайти снова.</p>
              </article>
              <article className="checklist-item">
                <strong>Если статус не меняется слишком долго</strong>
                <p>Нажмите “Проверить статус” и при необходимости напишите куратору или администратору.</p>
              </article>
            </div>
          </section>
        </div>
        {debugPanel}
      </OnboardingLayout>
    )
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">{isTeacherMode ? 'Universe Teacher' : 'Universe Student'}</p>
          <h1>{profile?.full_name || session?.user.full_name}</h1>
          <p className="hero-subtitle">
            {isTeacherMode ? 'Занятия, QR, отметки и сообщения в Telegram.' : 'Расписание, QR-отметка и причины отсутствия в Telegram.'}
          </p>
          <div className="hero-badges">
            <span className="hero-badge">{isTeacherMode ? teacherGroupLabel : activeGroupLabel}</span>
            <span className="hero-badge">{profile?.phone_number || session?.user.phone_number || 'Телефон не указан'}</span>
            <span className="hero-badge">
              {isTeacherMode
                ? `${teacherLessons.length} занятий`
                : latestRating
                  ? `Рейтинг ${latestRating.score}`
                  : `Присутствовал ${summary?.present ?? 0} раз`}
            </span>
          </div>
        </div>
        <div className="hero-card">
          <span>{isTeacherMode ? 'Ближайшее занятие' : 'Следующее занятие'}</span>
          <strong>{(isTeacherMode ? nextTeacherLesson?.discipline_name : nextLesson?.discipline_name) || 'Нет занятий'}</strong>
          <small>
            {isTeacherMode
              ? nextTeacherLesson
                ? `${formatDateTime(nextTeacherLesson.starts_at)} · ${nextTeacherLesson.group_name} · ${nextTeacherLesson.room || 'Аудитория уточняется'}`
                : 'Занятий пока нет'
              : nextLesson
                ? `${formatDateTime(nextLesson.starts_at)} · ${nextLesson.room || 'Аудитория уточняется'}`
                : 'Расписание пока пустое'}
          </small>
          <div className="hero-actions">
            <button type="button" className="secondary-button" onClick={() => setActiveTab(isTeacherMode ? 'teacher-lessons' : 'schedule')}>
              {isTeacherMode ? 'К занятиям' : 'К расписанию'}
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                if (isTeacherMode) {
                  void generateTeacherQr(selectedTeacherLesson?.id)
                  return
                }
                setActiveTab('qr')
              }}
            >
              {isTeacherMode ? 'Показать QR' : 'Сканировать код'}
            </button>
            {debugEnabled ? (
              <button type="button" className="ghost-button" onClick={() => setDebugOpen((current) => !current)}>
                {debugOpen ? 'Скрыть диагностику' : 'Диагностика'}
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <nav className="tab-bar" aria-label="Навигация Telegram кабинета">
        {activeTabs.map((tab) => (
          <button
            key={tab.key}
            className={tab.key === activeTab ? 'tab active' : 'tab'}
            onClick={() => {
              setGlobalError(null)
              setActiveTab(tab.key)
              if (tab.key === 'history') {
                void loadHistory()
              }
            }}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {globalError ? <p className="message error">{globalError}</p> : null}

      <main className="content-grid">
        {activeTab === 'home' ? (
          isTeacherMode ? (
          <>
            <section className="panel">
              <div className="section-head">
                <div>
                  <h2>Сегодня в Telegram</h2>
                  <p className="muted">Короткий рабочий срез по занятиям, QR и заявкам студентов.</p>
                </div>
                <span className={pendingTeacherReasons.length > 0 ? 'pill pending' : 'pill accepted'}>
                  {pendingTeacherReasons.length > 0 ? 'Есть заявки' : 'Спокойно'}
                </span>
              </div>
              <div className="student-stat-grid">
                <article className="student-stat-card student-stat-card-primary">
                  <span>Занятия</span>
                  <strong>{teacherLessons.length}</strong>
                  <small>Доступны для просмотра и отметок.</small>
                </article>
                <article className="student-stat-card student-stat-card-present">
                  <span>Группы</span>
                  <strong>{teacherGroups.length}</strong>
                  <small>Группы для рассылок.</small>
                </article>
                <article className="student-stat-card student-stat-card-late">
                  <span>Причины</span>
                  <strong>{pendingTeacherReasons.length}</strong>
                  <small>Ожидают решения.</small>
                </article>
                <article className="student-stat-card student-stat-card-risk">
                  <span>Отметки</span>
                  <strong>{teacherAttendanceMarked}/{teacherAttendanceTotal}</strong>
                  <small>По открытому занятию.</small>
                </article>
              </div>
            </section>
            <section className="panel">
              <h2>Ближайшее занятие</h2>
              {teacherLoading ? (
                <p>Загружаем данные...</p>
              ) : nextTeacherLesson ? (
                <TeacherLessonCard
                  item={nextTeacherLesson}
                  onQr={generateTeacherQr}
                  onAttendance={loadTeacherAttendance}
                  compact
                />
              ) : (
                <p>Занятий пока нет.</p>
              )}
            </section>
            <section className="panel">
              <div className="section-head">
                <h2>Очередь причин</h2>
                <button type="button" onClick={() => setActiveTab('teacher-reasons')}>Открыть</button>
              </div>
              {pendingTeacherReasons.length === 0 ? (
                <p>Нет причин на проверке.</p>
              ) : (
                pendingTeacherReasons.slice(0, 3).map((reason) => <TeacherReasonCard key={reason.id} item={reason} />)
              )}
            </section>
            <section className="panel">
              <div className="section-head">
                <h2>Быстрые действия</h2>
                <span className="pill accepted">{teacherGroupLabel}</span>
              </div>
              <div className="quick-actions">
                <button type="button" className="primary-button" onClick={() => void generateTeacherQr(selectedTeacherLesson?.id)}>
                  QR для занятия
                </button>
                <button type="button" className="secondary-button" onClick={() => void loadTeacherAttendance(selectedTeacherLesson?.id)}>
                  Открыть отметки
                </button>
                <button type="button" className="secondary-button" onClick={() => setActiveTab('teacher-broadcast')}>
                  Написать группе
                </button>
              </div>
            </section>
          </>
          ) : (
          <>
            <section className="panel">
              <div className="section-head">
                <div>
                  <h2>Статистика по посещаемости</h2>
                  <p className="muted">Короткий срез, чтобы сразу понять дисциплину входа и риск по пропускам.</p>
                </div>
                <span className={warnings.length > 0 ? 'pill pending' : 'pill accepted'}>{riskStatusLabel}</span>
              </div>
              <div className="student-stat-grid">
                <article className="student-stat-card student-stat-card-primary">
                  <span>Coverage</span>
                  <strong>{attendanceCoverage}%</strong>
                  <small>Отмеченные занятия от всего массива.</small>
                </article>
                <article className="student-stat-card student-stat-card-present">
                  <span>Присутствовал</span>
                  <strong>{summary?.present ?? 0}</strong>
                  <small>Чистые отметки без late.</small>
                </article>
                <article className="student-stat-card student-stat-card-late">
                  <span>Опоздания</span>
                  <strong>{summary?.late ?? 0}</strong>
                  <small>Вход после дедлайна пары.</small>
                </article>
                <article className="student-stat-card student-stat-card-risk">
                  <span>Risk-сигналы</span>
                  <strong>{warnings.length}</strong>
                  <small>Активные предупреждения по риску.</small>
                </article>
              </div>
            </section>
            <section className="panel">
              <h2>Ближайшее занятие</h2>
              {homeLoading ? (
                <p>Загружаем данные...</p>
              ) : nextLesson ? (
                <LessonCard item={nextLesson} compact onPredeclare={startPredeclaredReason} />
              ) : (
                <p>Ближайших занятий не найдено.</p>
              )}
            </section>
            <section className="panel">
              <div className="section-head">
                <div>
                  <h2>Сводка и рейтинг</h2>
                  <p className="muted">Разбивка по посещаемости и текущему академическому сигналу.</p>
                </div>
                <span className="pill accepted">Пунктуальность {punctualityRate}%</span>
              </div>
              {summary ? (
                <div className="stack-list">
                  <div className="attendance-ribbon">
                    <div className="attendance-ribbon-track" aria-hidden="true">
                      <span
                        className="attendance-ribbon-segment attendance-ribbon-segment-present"
                        style={{ flexGrow: summary.present === 0 ? 0 : summary.present / Math.max(totalTrackedEvents, 1) }}
                      />
                      <span
                        className="attendance-ribbon-segment attendance-ribbon-segment-late"
                        style={{ flexGrow: summary.late === 0 ? 0 : summary.late / Math.max(totalTrackedEvents, 1) }}
                      />
                      <span
                        className="attendance-ribbon-segment attendance-ribbon-segment-absent"
                        style={{ flexGrow: summary.absent === 0 ? 0 : summary.absent / Math.max(totalTrackedEvents, 1) }}
                      />
                    </div>
                    <div className="attendance-ribbon-legend">
                      <div><span className="pill present">present</span><strong>{summary.present}</strong></div>
                      <div><span className="pill late">late</span><strong>{summary.late}</strong></div>
                      <div><span className="pill absent">absent</span><strong>{summary.absent}</strong></div>
                    </div>
                  </div>
                  <div className="student-stat-grid">
                    <article className="student-stat-card">
                      <span>Пропусков всего</span>
                      <strong>{summary.absent}</strong>
                      <small>Все пропуски по текущему периоду.</small>
                    </article>
                    <article className="student-stat-card">
                      <span>Уважительных</span>
                      <strong>{summary.excused_absent}</strong>
                      <small>Подтверждены или приняты преподавателем.</small>
                    </article>
                    <article className="student-stat-card student-stat-card-risk">
                      <span>Неуважительных</span>
                      <strong>{summary.unexcused_absent}</strong>
                      <small>Главный фактор эскалаций и риска.</small>
                    </article>
                  </div>
                  {latestRating ? (
                    <div className="rating-spotlight">
                      <div>
                        <strong>Текущий рейтинг: {latestRating.score}</strong>
                        <small>Посещаемость {latestRating.attendance_pct}% и живая дисциплина по отметкам.</small>
                      </div>
                      <div className="rating-meta-grid">
                        <article className="rating-meta-card">
                          <span>Attendance</span>
                          <strong>{latestRating.attendance_pct}%</strong>
                        </article>
                        <article className="rating-meta-card">
                          <span>Late</span>
                          <strong>{latestRating.late_count}</strong>
                        </article>
                        <article className="rating-meta-card">
                          <span>Unexcused</span>
                          <strong>{latestRating.unexcused_absence_count}</strong>
                        </article>
                      </div>
                    </div>
                  ) : (
                    <p className="muted">Рейтинг еще не рассчитан.</p>
                  )}
                </div>
              ) : (
                <p>Сводка пока недоступна.</p>
              )}
            </section>
            <section className="panel">
              <h2>Предупреждения</h2>
              {warnings.length === 0 ? (
                <p>Вы не в зоне риска.</p>
              ) : (
                warnings.slice(0, 3).map((item) => <WarningCard key={item.id} item={item} />)
              )}
            </section>
            <section className="panel">
              <h2>Последние причины отсутствия</h2>
              {reasons.length === 0 ? <p>Причины отсутствия пока не отправлялись.</p> : reasons.slice(0, 3).map((reason) => <ReasonCard key={reason.id} item={reason} />)}
            </section>
          </>
          )
        ) : null}

        {activeTab === 'schedule' ? (
          <section className="panel wide-panel">
            <h2>Расписание</h2>
            {schedule.length === 0 ? (
              <p>Расписание пока пустое.</p>
            ) : (
              schedule.map((item) => (
                <LessonCard
                  key={item.id}
                  item={item}
                  onPredeclare={startPredeclaredReason}
                />
              ))
            )}
          </section>
        ) : null}

        {activeTab === 'qr' ? (
          <section className="panel wide-panel">
            <h2>Отметка по QR</h2>
            <p>Сканируйте QR преподавателя через Telegram или вставьте токен либо deeplink вручную.</p>
            <div className="qr-actions">
              <button className="primary-button" type="button" onClick={scanQrWithTelegram} disabled={qrBusy}>
                Открыть сканер Telegram
              </button>
              <form
                className="inline-form"
                onSubmit={(event) => {
                  event.preventDefault()
                  if (!extractQrToken(qrInput)) {
                    setQrMessage('Вставьте QR токен или deeplink.')
                    return
                  }
                  void submitQrToken(qrInput)
                }}
              >
                <input
                  value={qrInput}
                  onChange={(event) => setQrInput(event.target.value)}
                  placeholder="qr_xxx, JWT или t.me-ссылка"
                />
                <button type="submit" disabled={qrBusy}>Отметить</button>
              </form>
            </div>
            {qrMessage ? <p className="message">{qrMessage}</p> : null}
          </section>
        ) : null}

        {activeTab === 'history' ? (
          <section className="panel wide-panel">
            <div className="section-head">
              <h2>История посещаемости</h2>
              <button type="button" onClick={() => void loadHistory(true)} disabled={historyLoading}>Обновить</button>
            </div>
            {historyLoading ? <p>Загружаем историю...</p> : history.length === 0 ? <p>История посещаемости пока пуста.</p> : history.map((item) => <HistoryCard key={item.lesson_id} item={item} />)}
          </section>
        ) : null}

        {activeTab === 'reasons' ? (
          <>
            <section className="panel">
              <h2>Отправить причину отсутствия</h2>
              <form className="panel-form" onSubmit={submitAbsenceReason}>
                {schedule.length === 0 ? (
                  <p className="message subtle">Сначала дождитесь занятия в расписании. После этого можно будет отправить причину отсутствия.</p>
                ) : null}
                <label>
                  <span>Занятие</span>
                  <select value={reasonLessonId} onChange={(event) => setReasonLessonId(event.target.value)} disabled={schedule.length === 0}>
                    <option value="">Выберите занятие</option>
                    {schedule.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.discipline_name} · {formatDateTime(item.starts_at)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Тип причины</span>
                  <select value={reasonType} onChange={(event) => setReasonType(event.target.value)} disabled={schedule.length === 0}>
                    <option value="illness">Болезнь</option>
                    <option value="academic">Академическая</option>
                    <option value="personal">Личная</option>
                    <option value="other">Другое</option>
                  </select>
                </label>
                <label>
                  <span>Комментарий</span>
                  <textarea value={reasonComment} onChange={(event) => setReasonComment(event.target.value)} rows={4} placeholder="Коротко опишите причину." disabled={schedule.length === 0} />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={reasonPredeclared} onChange={(event) => setReasonPredeclared(event.target.checked)} disabled={schedule.length === 0} />
                  <span>Не смогу присутствовать заранее</span>
                </label>
                <label>
                  <span>Вложение</span>
                  <input type="file" onChange={(event) => setReasonFile(event.target.files?.[0] || null)} disabled={schedule.length === 0} />
                </label>
                {reasonMessage ? <p className="message">{reasonMessage}</p> : null}
                <button className="primary-button" type="submit" disabled={reasonBusy || schedule.length === 0}>
                  {reasonBusy ? 'Отправляем...' : reasonPredeclared ? 'Заявить заранее' : 'Отправить'}
                </button>
              </form>
            </section>
            <section className="panel">
              <h2>Мои причины отсутствия</h2>
              {reasons.length === 0 ? <p>Причины отсутствия еще не отправлялись.</p> : reasons.map((item) => <ReasonCard key={item.id} item={item} />)}
            </section>
          </>
        ) : null}

        {activeTab === 'faq' ? (
          <>
            <section className="panel">
              <div className="section-head">
                <h2>Профиль</h2>
                <span className="pill accepted">{activeGroupLabel}</span>
              </div>
              <div className="profile-grid">
                <ProfileFact label="Имя" value={profile?.full_name || session?.user.full_name} />
                <ProfileFact label="Логин" value={profile?.username || session?.user.username} />
                <ProfileFact label="Email" value={profile?.email || 'Не указан'} />
                <ProfileFact label="Телефон" value={profile?.phone_number || session?.user.phone_number || 'Не указан'} />
              </div>
            </section>
            <section className="panel">
              <div className="section-head">
                <h2>FAQ</h2>
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void searchFaq()
                  }}
                >
                  <input value={faqQuery} onChange={(event) => setFaqQuery(event.target.value)} placeholder="Поиск по FAQ" />
                  <button type="submit" disabled={faqLoading}>Искать</button>
                </form>
              </div>
              {faqCategories.length > 0 ? (
                <div className="chip-row" role="tablist" aria-label="Категории FAQ">
                  <button
                    type="button"
                    className={faqCategoryId ? 'chip' : 'chip active'}
                    onClick={() => {
                      setFaqCategoryId('')
                      void searchFaq(faqQuery, '')
                    }}
                  >
                    Все
                  </button>
                  {faqCategories.map((category) => (
                    <button
                      key={category.id}
                      type="button"
                      className={faqCategoryId === category.id ? 'chip active' : 'chip'}
                      onClick={() => {
                        setFaqCategoryId(category.id)
                        void searchFaq(faqQuery, category.id)
                      }}
                    >
                      {category.name}
                    </button>
                  ))}
                </div>
              ) : null}
              {faqLoading ? <p>Ищем ответы...</p> : faqItems.length === 0 ? <p>Подходящих FAQ не найдено.</p> : faqItems.map((item) => <FaqCard key={item.id} item={item} />)}
            </section>
          </>
        ) : null}

        {activeTab === 'teacher-lessons' ? (
          <section className="panel wide-panel">
            <div className="section-head">
              <h2>Занятия</h2>
              <button type="button" onClick={() => sessionRef.current && void loadTeacherData(sessionRef.current)} disabled={teacherLoading}>
                {teacherLoading ? 'Обновляем...' : 'Обновить'}
              </button>
            </div>
            {teacherLessons.length === 0 ? (
              <p>Занятий пока нет.</p>
            ) : (
              <div className="teacher-list">
                {teacherLessons.map((item) => (
                  <TeacherLessonCard
                    key={item.id}
                    item={item}
                    onQr={generateTeacherQr}
                    onAttendance={loadTeacherAttendance}
                  />
                ))}
              </div>
            )}
          </section>
        ) : null}

        {activeTab === 'teacher-qr' ? (
          <>
            <section className="panel">
              <h2>QR для занятия</h2>
              <div className="panel-form">
                <label>
                  <span>Занятие</span>
                  <select value={selectedTeacherLessonId} onChange={(event) => setSelectedTeacherLessonId(event.target.value)}>
                    <option value="">Выберите занятие</option>
                    {teacherLessons.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.discipline_name} · {item.group_code} · {formatDateTime(item.starts_at)}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="primary-button" type="button" disabled={teacherQrBusy} onClick={() => void generateTeacherQr()}>
                  {teacherQrBusy ? 'Генерируем...' : 'Сгенерировать QR'}
                </button>
              </div>
              {teacherMessage ? <p className="message">{teacherMessage}</p> : null}
            </section>
            <section className="panel">
              {teacherQr ? (
                <div className="teacher-qr-layout">
                  <div>
                    <div className="section-head">
                      <h2>Готово</h2>
                      <span className="pill accepted">До {formatDateTime(teacherQr.expires_at)}</span>
                    </div>
                    <p className="code-block">{normalizeTelegramLink(teacherQr.deeplink)}</p>
                    <div className="quick-actions">
                      <button type="button" className="primary-button" onClick={openTeacherQrLink}>Открыть ссылку</button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => {
                          void navigator.clipboard?.writeText(normalizeTelegramLink(teacherQr.deeplink))
                          setTeacherMessage('Ссылка скопирована.')
                        }}
                      >
                        Копировать
                      </button>
                    </div>
                  </div>
                  <div className="teacher-qr-box">
                    <QRCode value={normalizeTelegramLink(teacherQr.deeplink)} size={220} />
                  </div>
                </div>
              ) : (
                <p>Выберите занятие и сгенерируйте QR.</p>
              )}
            </section>
          </>
        ) : null}

        {activeTab === 'teacher-attendance' ? (
          <section className="panel wide-panel">
            <div className="section-head">
              <div>
                <h2>Отметки</h2>
                <p className="muted">
                  {teacherAttendance?.lesson
                    ? `${teacherAttendance.lesson.group_name} · ${teacherAttendance.lesson.discipline_name}`
                    : 'Выберите занятие для просмотра.'}
                </p>
              </div>
              <div className="inline-form">
                <select value={selectedTeacherLessonId} onChange={(event) => setSelectedTeacherLessonId(event.target.value)}>
                  <option value="">Занятие</option>
                  {teacherLessons.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.discipline_name} · {item.group_code}
                    </option>
                  ))}
                </select>
                <button type="button" onClick={() => void loadTeacherAttendance()} disabled={teacherAttendanceBusy}>
                  {teacherAttendanceBusy ? 'Загружаем...' : 'Открыть'}
                </button>
              </div>
            </div>
            {teacherMessage ? <p className="message">{teacherMessage}</p> : null}
            {teacherAttendance ? (
              <div className="teacher-roster">
                {teacherAttendance.students.map((student) => (
                  <article key={student.student_id} className="info-card roster-card">
                    <div className="info-head">
                      <strong>{student.full_name}</strong>
                      <span className={`pill ${student.status || 'pending'}`}>{humanizeStatus(student.status)}</span>
                    </div>
                    <small>{student.username ? `@${student.username}` : 'username не указан'}</small>
                    <small>{student.source ? `Источник: ${humanizeStatus(student.source)}` : 'Источник не указан'}</small>
                    <div className="roster-controls">
                      <select
                        value={teacherStatusDrafts[student.student_id] || student.status || ''}
                        onChange={(event) =>
                          setTeacherStatusDrafts((current) => ({
                            ...current,
                            [student.student_id]: event.target.value as 'present' | 'late' | 'absent',
                          }))
                        }
                      >
                        <option value="">Статус</option>
                        <option value="present">Присутствовал</option>
                        <option value="late">Опоздал</option>
                        <option value="absent">Отсутствовал</option>
                      </select>
                      <input
                        value={teacherCorrectionDrafts[student.student_id] || ''}
                        onChange={(event) =>
                          setTeacherCorrectionDrafts((current) => ({
                            ...current,
                            [student.student_id]: event.target.value,
                          }))
                        }
                        placeholder="Причина корректировки"
                      />
                      <button type="button" className="primary-button" disabled={teacherAttendanceBusy} onClick={() => void correctTeacherAttendance(student.student_id)}>
                        Сохранить
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p>Откройте занятие, чтобы увидеть список студентов.</p>
            )}
          </section>
        ) : null}

        {activeTab === 'teacher-reasons' ? (
          <section className="panel wide-panel">
            <div className="section-head">
              <h2>Причины отсутствия</h2>
              <button type="button" onClick={() => sessionRef.current && void loadTeacherData(sessionRef.current)} disabled={teacherLoading}>
                {teacherLoading ? 'Обновляем...' : 'Обновить'}
              </button>
            </div>
            {teacherMessage ? <p className="message">{teacherMessage}</p> : null}
            {teacherReasons.length === 0 ? (
              <p>Причин отсутствия пока нет.</p>
            ) : (
              <div className="teacher-list">
                {teacherReasons.map((reason) => (
                  <TeacherReasonCard
                    key={reason.id}
                    item={reason}
                    comment={teacherModerationDrafts[reason.id] || ''}
                    busy={teacherReasonBusy === reason.id}
                    onComment={(value) =>
                      setTeacherModerationDrafts((current) => ({
                        ...current,
                        [reason.id]: value,
                      }))
                    }
                    onAccept={() => void moderateTeacherReason(reason.id, 'accepted')}
                    onReject={() => void moderateTeacherReason(reason.id, 'rejected')}
                  />
                ))}
              </div>
            )}
          </section>
        ) : null}

        {activeTab === 'teacher-broadcast' ? (
          <section className="panel">
            <h2>Рассылка группе</h2>
            <form className="panel-form" onSubmit={sendTeacherBroadcast}>
              <label>
                <span>Группа</span>
                <select value={teacherBroadcastGroupId} onChange={(event) => setTeacherBroadcastGroupId(event.target.value)}>
                  <option value="">Выберите группу</option>
                  {teacherGroups.map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.code} · {group.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Сообщение</span>
                <textarea
                  value={teacherBroadcastMessage}
                  onChange={(event) => setTeacherBroadcastMessage(event.target.value)}
                  rows={6}
                  maxLength={2000}
                  placeholder="Текст для студентов"
                />
              </label>
              {teacherMessage ? <p className="message">{teacherMessage}</p> : null}
              <button className="primary-button" type="submit" disabled={teacherBroadcastBusy}>
                {teacherBroadcastBusy ? 'Отправляем...' : 'Отправить'}
              </button>
            </form>
          </section>
        ) : null}
      </main>

      {debugPanel}
    </div>
  )
}

function Splash({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  return (
    <div className="splash">
      <div className="content-grid splash-grid">
        <div className="panel splash-card">
          <p className="eyebrow">Universe Student</p>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {children}
      </div>
    </div>
  )
}

function OnboardingLayout({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <div className="splash">
      <div className="onboarding-grid">
        <section className="panel splash-card">
          <p className="eyebrow">Universe Student</p>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </section>
        {children}
      </div>
    </div>
  )
}

function DebugPanel({ events }: { events: DebugEvent[] }) {
  return (
    <section className="panel debug-panel">
      <h2>Диагностика Telegram Mini App</h2>
      <p className="debug-subtitle">На экране показано, что реально видит фронтенд: Telegram SDK, initData, env URL и ответы API.</p>
      {events.length === 0 ? (
        <p>Ожидаем первые события...</p>
      ) : (
        <div className="debug-events">
          {[...events].reverse().map((event, index) => (
            <article key={`${event.timestamp}-${index}`} className="debug-event">
              <div className="debug-event-head">
                <strong>{event.title}</strong>
                <span>{event.timestamp}</span>
              </div>
              <pre>{formatDebugValue(event.data)}</pre>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function StatusTile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <article className="status-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}

function ProfileFact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <article className="profile-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}

function LessonCard({
  item,
  compact = false,
  onPredeclare,
}: {
  item: ScheduleItem
  compact?: boolean
  onPredeclare?: (lessonId: string) => void
}) {
  return (
    <article className={compact ? 'lesson-card compact' : 'lesson-card'}>
      <div>
        <strong>{item.discipline_name}</strong>
        <span>{item.group_name} · {item.teacher_name}</span>
      </div>
      <div className="lesson-meta">
        <span>{formatDateTime(item.starts_at)}</span>
        <span>{item.room || 'Аудитория уточняется'}</span>
        <span>Окно отметки до {formatDateTime(item.attendance_window_closes_at)}</span>
      </div>
      {!compact ? (
        <div className="card-actions">
          <button type="button" className="secondary-button" onClick={() => onPredeclare?.(item.id)}>
            Не смогу присутствовать
          </button>
        </div>
      ) : null}
    </article>
  )
}

function TeacherLessonCard({
  item,
  compact = false,
  onQr,
  onAttendance,
}: {
  item: TeacherLessonItem
  compact?: boolean
  onQr?: (lessonId: string) => void
  onAttendance?: (lessonId: string) => void
}) {
  return (
    <article className={compact ? 'lesson-card compact' : 'lesson-card'}>
      <div>
        <strong>{item.discipline_name}</strong>
        <span>{item.group_name} · {item.group_code}</span>
      </div>
      <div className="lesson-meta">
        <span>{formatDateTime(item.starts_at)}</span>
        <span>{item.room || 'Аудитория уточняется'}</span>
        <span className={`pill ${item.status}`}>{humanizeStatus(item.status)}</span>
      </div>
      {!compact ? (
        <div className="card-actions">
          <button type="button" onClick={() => onQr?.(item.id)}>QR</button>
          <button type="button" className="secondary-button" onClick={() => onAttendance?.(item.id)}>
            Отметки
          </button>
        </div>
      ) : null}
    </article>
  )
}

function TeacherReasonCard({
  item,
  comment,
  busy = false,
  onComment,
  onAccept,
  onReject,
}: {
  item: TeacherAbsenceReasonItem
  comment?: string
  busy?: boolean
  onComment?: (value: string) => void
  onAccept?: () => void
  onReject?: () => void
}) {
  const interactive = Boolean(onAccept || onReject)
  return (
    <article className="info-card">
      <div className="info-head">
        <strong>{item.student_name}</strong>
        <span className={`pill ${item.status}`}>{humanizeStatus(item.status)}</span>
      </div>
      <p>{item.group_name} · {formatDateTime(item.lesson_starts_at)}</p>
      <p>{formatReasonType(item.reason_type)} · {item.comment || 'Без комментария'}</p>
      {item.is_predeclared ? <small>Заявлено заранее</small> : null}
      {item.attachments.length > 0 ? <small>Вложения: {item.attachments.map((file) => file.file_name).join(', ')}</small> : null}
      {interactive ? (
        <div className="teacher-reason-actions">
          <input value={comment || ''} onChange={(event) => onComment?.(event.target.value)} placeholder="Комментарий преподавателя" />
          <button type="button" className="primary-button" disabled={busy} onClick={onAccept}>
            Принять
          </button>
          <button type="button" className="secondary-button danger-button" disabled={busy} onClick={onReject}>
            Отклонить
          </button>
        </div>
      ) : null}
    </article>
  )
}

function HistoryCard({ item }: { item: HistoryItem }) {
  return (
    <article className="info-card">
      <div className="info-head">
        <strong>{item.discipline_name}</strong>
        <span className={`pill ${item.status}`}>{item.status}</span>
      </div>
      <p>{item.group_name} · {item.teacher_name}</p>
      <p>{formatDateTime(item.starts_at)} · {item.room || 'Аудитория уточняется'}</p>
      <small>Источник: {item.source}{item.correction_reason ? ` · ${item.correction_reason}` : ''}</small>
    </article>
  )
}

function ReasonCard({ item }: { item: AbsenceReasonItem }) {
  return (
    <article className="info-card">
      <div className="info-head">
        <strong>{item.discipline_name}</strong>
        <span className={`pill ${item.status}`}>{item.status}</span>
      </div>
      <p>{item.group_name} · {formatDateTime(item.lesson_starts_at)}</p>
      <p>{formatReasonType(item.reason_type)} · {item.comment || 'Без комментария'}</p>
      {item.is_predeclared ? <small>Заявлено заранее</small> : null}
      {item.attachments.length > 0 ? <small>Вложения: {item.attachments.map((file) => file.file_name).join(', ')}</small> : null}
    </article>
  )
}

function WarningCard({ item }: { item: WarningItem }) {
  return (
    <article className="info-card">
      <div className="info-head">
        <strong>Риск-событие</strong>
        <span className={`pill ${item.status}`}>{item.status}</span>
      </div>
      <p>{formatWarningReason(item.reason)}</p>
      <small>{formatDateTime(item.created_at)}</small>
    </article>
  )
}

function FaqCard({ item }: { item: FaqItem }) {
  const blocks = parseFaqAnswerBlocks(item.answer)
  const keywords = parseFaqKeywords(item.keywords)

  return (
    <article className="info-card faq-card">
      <small className="faq-category">{item.category_name}</small>
      <strong>{item.question}</strong>
      <div className="faq-answer">
        {blocks.length > 0
          ? blocks.map((block, index) =>
              block.type === 'list' ? (
                <ul key={`${item.id}-list-${index}`}>
                  {block.items.map((entry, entryIndex) => (
                    <li key={`${item.id}-list-${index}-${entryIndex}`}>{entry}</li>
                  ))}
                </ul>
              ) : (
                <p key={`${item.id}-paragraph-${index}`}>{block.content}</p>
              ),
            )
          : <p>{item.answer}</p>}
      </div>
      {keywords.length > 0 ? (
        <div className="faq-keywords" aria-label="Ключевые слова FAQ">
          {keywords.map((keyword) => (
            <span key={keyword} className="faq-keyword">{keyword}</span>
          ))}
        </div>
      ) : null}
    </article>
  )
}
