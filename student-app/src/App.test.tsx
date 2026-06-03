import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import App from './App'

function mockTelegram(
  initData = 'init-data',
  scannedValue = 'qr_dynamic_token',
) {
  const showScanQrPopup = vi.fn((_params, callback: (value: string) => boolean | void) => {
    callback(scannedValue)
  })
  window.Telegram = {
    WebApp: {
      initData,
      ready: vi.fn(),
      expand: vi.fn(),
      showScanQrPopup,
      closeScanQrPopup: vi.fn(),
    },
  }
  return showScanQrPopup
}

function mockFetch(handler: (url: string, init?: RequestInit) => Promise<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init)),
  )
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.Telegram = undefined
})

it('shows onboarding form and validates full name before sending a request', async () => {
  mockTelegram()
  let bootstrapCalls = 0
  mockFetch(async (url) => {
    if (url.includes('/webapp/bootstrap')) {
      bootstrapCalls += 1
      if (bootstrapCalls === 1) {
        return jsonResponse({ status: 'link_required' })
      }
      return jsonResponse({
        status: 'pending',
        requested_full_name: 'Иванов Иван',
        group_code: 'SE-101',
        note: null,
      })
    }
    if (url.includes('/webapp/binding-request')) {
      return jsonResponse({ status: 'pending', message: 'Binding request submitted' })
    }
    return jsonResponse({})
  })

  render(<App />)

  expect(await screen.findByRole('heading', { name: /создание доступа/i })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: /диагностика telegram mini app/i })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /отправить заявку/i }))
  expect(await screen.findByText(/введите полное имя/i)).toBeInTheDocument()

  await userEvent.type(screen.getByPlaceholderText(/иванов иван/i), 'Иванов Иван')
  await userEvent.type(screen.getByPlaceholderText(/se-101/i), 'SE-101')
  await userEvent.click(screen.getByRole('button', { name: /отправить заявку/i }))

  expect(await screen.findByRole('heading', { name: /заявка отправлена/i })).toBeInTheDocument()
  expect(screen.getAllByText(/SE-101/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/binding request submitted/i).length).toBeGreaterThan(0)
})

it('shows rejected state from bootstrap', async () => {
  mockTelegram()
  mockFetch(async (url) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({ status: 'rejected', message: 'Проверьте данные', requested_full_name: 'Иванов Иван' })
    }
    return jsonResponse({})
  })

  render(<App />)
  expect(await screen.findByRole('heading', { name: /заявка отклонена/i })).toBeInTheDocument()
  await waitFor(() => {
    expect(screen.getByDisplayValue('Иванов Иван')).toBeInTheDocument()
  })
})

it('renders linked student data and schedule cards', async () => {
  mockTelegram()
  mockFetch(async (url) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse([
        {
          id: 'lesson-1',
          group_id: 'group-1',
          group_code: 'SE-101',
          group_name: 'SE-101',
          discipline_id: 'disc-1',
          discipline_code: 'DB',
          discipline_name: 'Databases',
          teacher_id: 'teacher-1',
          teacher_name: 'Teacher API',
          starts_at: '2026-03-16T10:00:00Z',
          ends_at: '2026-03-16T11:00:00Z',
          status: 'planned',
          room: 'A-101',
          attendance_window_opens_at: '2026-03-16T09:55:00Z',
          attendance_window_closes_at: '2026-03-16T10:15:00Z',
          late_after: '2026-03-16T10:20:00Z',
        },
      ])
    }
    if (url.includes('/student/attendance/summary')) {
      return jsonResponse({ present: 12, late: 2, absent: 1, excused_absent: 1, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([
        {
          score: 94,
          attendance_pct: 96,
          late_count: 2,
          unexcused_absence_count: 0,
          period_start: '2026-03-01',
          period_end: '2026-03-31',
        },
      ])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([
        {
          id: 'warn-1',
          status: 'triggered',
          reason: { late_count: 2 },
          created_at: '2026-03-16T09:00:00Z',
        },
      ])
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([
        {
          id: 'faq-1',
          category_id: 'cat-1',
          category_name: 'Регистрация',
          question: 'Как привязать Telegram?',
          answer: 'Откройте mini app и отправьте заявку.',
          keywords: 'telegram, регистрация',
        },
      ])
    }
    return jsonResponse([])
  })

  render(<App />)
  expect(await screen.findByRole('heading', { name: /test student/i })).toBeInTheDocument()
  expect(screen.getAllByText(/Databases/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/Teacher API/).length).toBeGreaterThan(0)
  expect(screen.getByText(/текущий рейтинг: 94/i)).toBeInTheDocument()
  expect(screen.getByText(/риск-событие/i)).toBeInTheDocument()
})

it('requests student attendance summary with a default date range', async () => {
  mockTelegram()
  let summaryUrl = ''
  mockFetch(async (url) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse([])
    }
    if (url.includes('/student/attendance/summary')) {
      summaryUrl = url
      return jsonResponse({ present: 0, late: 0, absent: 0, excused_absent: 0, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([])
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([])
    }
    return jsonResponse([])
  })

  render(<App />)
  expect(await screen.findByRole('heading', { name: /test student/i })).toBeInTheDocument()

  await waitFor(() => {
    expect(summaryUrl).toContain('/student/attendance/summary?')
  })

  const summarySearchParams = new URL(summaryUrl, window.location.origin).searchParams
  expect(summarySearchParams.get('date_from')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  expect(summarySearchParams.get('date_to')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
})

it('formats FastAPI validation errors without rendering object objects', async () => {
  mockTelegram()
  mockFetch(async (url) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse(
        {
          detail: [
            { loc: ['body', 'date_from'], msg: 'Input should be a valid date' },
            { loc: ['body', 'date_to'], msg: 'Input should be a valid date' },
          ],
        },
        422,
      )
    }
    if (url.includes('/student/attendance/summary')) {
      return jsonResponse({ present: 0, late: 0, absent: 0, excused_absent: 0, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([])
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([])
    }
    return jsonResponse([])
  })

  render(<App />)

  expect(await screen.findByRole('heading', { name: /test student/i })).toBeInTheDocument()
  expect(await screen.findByText(/date_from: input should be a valid date; date_to: input should be a valid date/i)).toBeInTheDocument()
  expect(screen.queryByText(/\[object Object\]/i)).not.toBeInTheDocument()
})

it('renders linked teacher flow with QR, attendance correction and broadcast', async () => {
  mockTelegram()
  let correctionPayload: { lesson_id?: string; student_id?: string; status?: string; reason?: string } | null = null
  let broadcastUrl = ''
  mockFetch(async (url, init) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'teacher-access',
          refresh_token: 'teacher-refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'teacher-1',
          username: 'teacher',
          full_name: 'Test Teacher',
          email: null,
          phone_number: '+70000000002',
          roles: ['teacher'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/teacher/lessons/lesson-1/attendance')) {
      return jsonResponse({
        lesson: {
          id: 'lesson-1',
          group_id: 'group-1',
          group_code: 'SE-101',
          group_name: 'SE-101',
          discipline_id: 'disc-1',
          discipline_code: 'DB',
          discipline_name: 'Databases',
          starts_at: '2026-03-16T10:00:00Z',
          ends_at: '2026-03-16T11:00:00Z',
          status: 'planned',
          room: 'A-101',
        },
        students: [
          {
            student_id: 'student-1',
            username: 'student',
            full_name: 'Student One',
            attendance_id: null,
            status: null,
            source: null,
            marked_at: null,
            is_excused: false,
            correction_reason: null,
          },
        ],
      })
    }
    if (url.includes('/teacher/lessons')) {
      return jsonResponse([
        {
          id: 'lesson-1',
          group_id: 'group-1',
          group_code: 'SE-101',
          group_name: 'SE-101',
          discipline_id: 'disc-1',
          discipline_code: 'DB',
          discipline_name: 'Databases',
          starts_at: '2026-03-16T10:00:00Z',
          ends_at: '2026-03-16T11:00:00Z',
          status: 'planned',
          room: 'A-101',
        },
      ])
    }
    if (url.includes('/teacher/groups')) {
      return jsonResponse([{ id: 'group-1', code: 'SE-101', name: 'SE-101' }])
    }
    if (url.includes('/teacher/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/teacher/qr/generate')) {
      return jsonResponse({
        token: 'static-token',
        deeplink: 't.me/universe_bot?start=qr_static-token',
        expires_at: '2026-03-16T10:15:00Z',
      })
    }
    if (url.includes('/teacher/attendance/correct')) {
      correctionPayload = JSON.parse(String(init?.body || '{}'))
      return jsonResponse({ status: 'present' })
    }
    if (url.includes('/teacher/broadcasts')) {
      broadcastUrl = url
      return jsonResponse({ recipients: 1 })
    }
    return jsonResponse([])
  })

  render(<App />)
  expect(await screen.findByRole('heading', { name: /test teacher/i })).toBeInTheDocument()
  expect(screen.getByText(/Universe Teacher/i)).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: /показать qr/i }))
  expect(await screen.findByText(/https:\/\/t\.me\/universe_bot\?start=qr_static-token/i)).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: /отметки/i }))
  await userEvent.click(screen.getByRole('button', { name: /^открыть$/i }))
  expect(await screen.findByText(/student one/i)).toBeInTheDocument()
  await userEvent.selectOptions(screen.getAllByRole('combobox')[1], 'present')
  await userEvent.type(screen.getByPlaceholderText(/причина корректировки/i), 'Manual check')
  await userEvent.click(screen.getByRole('button', { name: /сохранить/i }))
  await waitFor(() => {
    expect(correctionPayload).toEqual({
      lesson_id: 'lesson-1',
      student_id: 'student-1',
      status: 'present',
      reason: 'Manual check',
    })
  })

  await userEvent.click(screen.getByRole('button', { name: /рассылки/i }))
  await userEvent.selectOptions(screen.getByRole('combobox'), 'group-1')
  await userEvent.type(screen.getByPlaceholderText(/текст для студентов/i), 'Проверьте обновление')
  await userEvent.click(screen.getByRole('button', { name: /отправить/i }))
  expect(await screen.findByText(/получателей: 1/i)).toBeInTheDocument()
  expect(new URL(broadcastUrl, window.location.origin).searchParams.get('message')).toBe('Проверьте обновление')
})

it('marks attendance from Telegram QR scanner and shows success message', async () => {
  const showScanQrPopup = mockTelegram(
    'init-data',
    'https://t.me/universe_bot?start=qr_dynamic.jwt.token',
  )
  let submittedQrToken: string | null = null
  mockFetch(async (url, init) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse([])
    }
    if (url.includes('/student/attendance/summary')) {
      return jsonResponse({ present: 0, late: 0, absent: 0, excused_absent: 0, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([])
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([])
    }
    if (url.includes('/student/attendance/mark-qr')) {
      const body = JSON.parse(String(init?.body || '{}')) as { qr_token?: string }
      submittedQrToken = body.qr_token ?? null
      return jsonResponse({ status: 'present' })
    }
    return jsonResponse([])
  })

  render(<App />)
  await screen.findByRole('heading', { name: /test student/i })
  await userEvent.click(screen.getByRole('button', { name: /QR/i }))
  await userEvent.click(screen.getByRole('button', { name: /открыть сканер telegram/i }))

  expect(showScanQrPopup).toHaveBeenCalled()
  expect(submittedQrToken).toBe('dynamic.jwt.token')
  expect(await screen.findByText(/посещаемость отмечена: present/i)).toBeInTheDocument()
})

it('submits absence reason form with multipart payload', async () => {
  mockTelegram()
  const fetchSpy = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse([
        {
          id: 'lesson-1',
          group_id: 'group-1',
          group_code: 'SE-101',
          group_name: 'SE-101',
          discipline_id: 'disc-1',
          discipline_code: 'DB',
          discipline_name: 'Databases',
          teacher_id: 'teacher-1',
          teacher_name: 'Teacher API',
          starts_at: '2026-03-16T10:00:00Z',
          ends_at: '2026-03-16T11:00:00Z',
          status: 'planned',
          room: 'A-101',
          attendance_window_opens_at: '2026-03-16T09:55:00Z',
          attendance_window_closes_at: '2026-03-16T10:15:00Z',
          late_after: '2026-03-16T10:20:00Z',
        },
      ])
    }
    if (url.includes('/student/attendance/summary')) {
      return jsonResponse({ present: 1, late: 0, absent: 0, excused_absent: 0, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([])
    }
    if (url.includes('/student/absence-reasons') && init?.method === 'POST') {
      const body = init.body as FormData
      expect(body.get('lesson_id')).toBe('lesson-1')
      expect(body.get('reason_type')).toBe('illness')
      expect(body.get('comment')).toBe('Doctor note')
      expect(body.get('is_predeclared')).toBe('true')
      return jsonResponse({ status: 'pending' })
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([
        {
          id: 'faq-1',
          category_id: 'cat-1',
          category_name: 'Регистрация',
          question: 'Как привязать Telegram?',
          answer: 'Откройте mini app и отправьте заявку.',
          keywords: 'telegram, регистрация',
        },
      ])
    }
    return jsonResponse([])
  })
  vi.stubGlobal('fetch', fetchSpy)

  render(<App />)
  await screen.findByRole('heading', { name: /test student/i })
  await userEvent.click(screen.getByRole('button', { name: /причины/i }))
  await userEvent.selectOptions(screen.getByRole('combobox', { name: /занятие/i }), 'lesson-1')
  await userEvent.type(screen.getByPlaceholderText(/коротко опишите причину/i), 'Doctor note')
  await userEvent.click(screen.getByRole('checkbox', { name: /не смогу присутствовать заранее/i }))
  await userEvent.click(screen.getByRole('button', { name: /заявить заранее/i }))

  await waitFor(() => {
    expect(screen.getByText(/предварительная причина отсутствия отправлена/i)).toBeInTheDocument()
  })
})

it('does not submit absence reason form when there are no lessons available', async () => {
  mockTelegram()
  const fetchSpy = vi.fn(async (url: string) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse([])
    }
    if (url.includes('/student/attendance/summary')) {
      return jsonResponse({ present: 0, late: 0, absent: 0, excused_absent: 0, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([])
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([])
    }
    return jsonResponse([])
  })
  vi.stubGlobal('fetch', fetchSpy)

  render(<App />)
  await screen.findByRole('heading', { name: /test student/i })
  await userEvent.click(screen.getByRole('button', { name: /причины/i }))

  expect(await screen.findByText(/сначала дождитесь занятия в расписании/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /отправить/i })).toBeDisabled()
  expect(screen.queryByText(/не удалось выполнить запрос/i)).not.toBeInTheDocument()
})

it('filters faq by category chips', async () => {
  mockTelegram()
  const fetchSpy = vi.fn(async (url: string) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse([])
    }
    if (url.includes('/student/attendance/summary')) {
      return jsonResponse({ present: 0, late: 0, absent: 0, excused_absent: 0, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([])
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq?category_id=cat-2')) {
      return jsonResponse([
        {
          id: 'faq-2',
          category_id: 'cat-2',
          category_name: 'Посещаемость',
          question: 'Как отметиться кнопкой?',
          answer: 'Откройте расписание и нажмите кнопку отметки.',
          keywords: 'кнопка, attendance',
        },
      ])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([
        {
          id: 'faq-1',
          category_id: 'cat-1',
          category_name: 'Регистрация',
          question: 'Как привязать Telegram?',
          answer: 'Откройте mini app и отправьте заявку.',
          keywords: 'telegram, регистрация',
        },
        {
          id: 'faq-2',
          category_id: 'cat-2',
          category_name: 'Посещаемость',
          question: 'Как отметиться кнопкой?',
          answer: 'Откройте расписание и нажмите кнопку отметки.',
          keywords: 'кнопка, attendance',
        },
      ])
    }
    return jsonResponse([])
  })
  vi.stubGlobal('fetch', fetchSpy)

  render(<App />)
  await screen.findByRole('heading', { name: /test student/i })
  await userEvent.click(screen.getByRole('button', { name: /faq \/ профиль/i }))
  await userEvent.click(screen.getByRole('button', { name: /посещаемость/i }))

  await waitFor(() => {
    expect(screen.getAllByText(/как отметиться кнопкой/i).length).toBeGreaterThan(0)
  })
})

it('renders faq answers as readable paragraphs and lists', async () => {
  mockTelegram()
  mockFetch(async (url: string) => {
    if (url.includes('/webapp/bootstrap')) {
      return jsonResponse({
        status: 'linked',
        tokens: {
          access_token: 'access',
          refresh_token: 'refresh',
          token_type: 'bearer',
          access_expires_at: '2026-03-16T00:00:00Z',
          refresh_expires_at: '2026-03-17T00:00:00Z',
          password_change_required: false,
        },
        user: {
          id: 'user-1',
          username: 'student',
          full_name: 'Test Student',
          email: null,
          phone_number: '+70000000001',
          roles: ['student'],
          is_active: true,
          must_change_password: false,
        },
      })
    }
    if (url.includes('/student/profile')) {
      return jsonResponse({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      })
    }
    if (url.includes('/student/schedule')) {
      return jsonResponse([])
    }
    if (url.includes('/student/attendance/summary')) {
      return jsonResponse({ present: 0, late: 0, absent: 0, excused_absent: 0, unexcused_absent: 0 })
    }
    if (url.includes('/student/rating')) {
      return jsonResponse([])
    }
    if (url.includes('/student/warnings')) {
      return jsonResponse([])
    }
    if (url.includes('/student/absence-reasons')) {
      return jsonResponse([])
    }
    if (url.includes('/student/faq')) {
      return jsonResponse([
        {
          id: 'faq-1',
          category_id: 'cat-1',
          category_name: 'Учебный процесс',
          question: 'Как оформить пропуск?',
          answer: 'Подготовьте короткое объяснение.\n\n- Выберите занятие\n- Добавьте комментарий\n- Прикрепите документ при необходимости',
          keywords: 'пропуск, причина, документ',
        },
      ])
    }
    return jsonResponse([])
  })

  render(<App />)
  await screen.findByRole('heading', { name: /test student/i })
  await userEvent.click(screen.getByRole('button', { name: /faq \/ профиль/i }))

  expect(await screen.findByText(/подготовьте короткое объяснение/i)).toBeInTheDocument()
  expect(screen.getByText(/выберите занятие/i)).toBeInTheDocument()
  expect(screen.getByText(/добавьте комментарий/i)).toBeInTheDocument()
  expect(screen.getByText(/прикрепите документ при необходимости/i)).toBeInTheDocument()
  expect(screen.getByText(/^пропуск$/i)).toBeInTheDocument()
  expect(screen.getByText(/^причина$/i)).toBeInTheDocument()
  expect(screen.getByText(/^документ$/i)).toBeInTheDocument()
})
