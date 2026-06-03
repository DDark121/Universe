import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

function attachConsoleGuards(page: Page) {
  const issues: string[] = []

  page.on('console', (message) => {
    if (!['error', 'warning'].includes(message.type())) {
      return
    }
    const text = message.text()
    if (text.includes('Download the React DevTools')) {
      return
    }
    issues.push(`${message.type()}: ${text}`)
  })

  page.on('pageerror', (error) => {
    issues.push(`pageerror: ${error.message}`)
  })

  return async () => {
    expect(issues).toEqual([])
  }
}

test('student mini app bootstrap, predeclare flow, and FAQ render', async ({ page }) => {
  const assertNoRuntimeIssues = attachConsoleGuards(page)
  let absencePosted = false
  let lastQrToken: string | null = null

  await page.route('https://telegram.org/js/telegram-web-app.js?61', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: `
        window.Telegram = {
          WebApp: {
            initData: 'playwright-init-data',
            initDataUnsafe: {},
            version: '6.0',
            platform: 'unknown',
            colorScheme: 'light',
            isExpanded: true,
            viewportHeight: 720,
            viewportStableHeight: 720,
            themeParams: {},
            ready: function () {},
            expand: function () {},
            showScanQrPopup: function (_params, callback) {
              callback('https://t.me/universe_test_bot?start=qr_dynamic.jwt.token');
            },
            closeScanQrPopup: function () {}
          }
        };
      `,
    })
  })

  await page.route('**/tg/webapp/bootstrap', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
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
      }),
    })
  })

  await page.route('**/api/v1/student/profile', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'user-1',
        username: 'student',
        full_name: 'Test Student',
        email: null,
        phone_number: '+70000000001',
      }),
    })
  })

  await page.route('**/api/v1/student/schedule', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
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
      ]),
    })
  })

  await page.route('**/api/v1/student/attendance/summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ present: 12, late: 2, absent: 1, excused_absent: 1, unexcused_absent: 0 }),
    })
  })

  await page.route('**/api/v1/student/rating', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          score: 94,
          attendance_pct: 96,
          late_count: 2,
          unexcused_absence_count: 0,
          period_start: '2026-03-01',
          period_end: '2026-03-31',
        },
      ]),
    })
  })

  await page.route('**/api/v1/student/warnings', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'warn-1',
          status: 'triggered',
          reason: { late_count: 2 },
          created_at: '2026-03-16T09:00:00Z',
        },
      ]),
    })
  })

  await page.route('**/api/v1/student/absence-reasons', async (route) => {
    if (route.request().method() === 'POST') {
      absencePosted = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ reason_id: 'reason-1', status: 'pending' }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        absencePosted
          ? [
              {
                id: 'reason-1',
                lesson_id: 'lesson-1',
                lesson_starts_at: '2026-03-16T10:00:00Z',
                discipline_name: 'Databases',
                group_name: 'SE-101',
                reason_type: 'illness',
                comment: '',
                is_predeclared: true,
                status: 'pending',
                moderation_comment: null,
                attachments: [],
              },
            ]
          : [],
      ),
    })
  })

  await page.route('**/api/v1/student/attendance/mark-qr', async (route) => {
    const body = route.request().postDataJSON() as { qr_token?: string }
    lastQrToken = body.qr_token ?? null
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'present' }),
    })
  })

  await page.route('**/api/v1/student/faq', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'faq-1',
          category_id: 'cat-1',
          category_name: 'Регистрация',
          question: 'Как привязать Telegram?',
          answer: 'Откройте mini app и отправьте заявку.',
          keywords: 'telegram, регистрация',
        },
      ]),
    })
  })

  await page.route('**/api/v1/public/client-errors', async (route) => {
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'accepted' }),
    })
  })

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Test Student' })).toBeVisible()
  await expect(page.getByText('Текущий рейтинг: 94')).toBeVisible()
  await expect(page.getByText('SE-101').first()).toBeVisible()
  await expect(page.getByText('+70000000001')).toBeVisible()
  await expect(page.getByRole('heading', { name: /диагностика telegram mini app/i })).toHaveCount(0)

  await page.getByRole('button', { name: 'Расписание' }).click()
  await expect(page.getByRole('main').getByText('Databases').first()).toBeVisible()
  await page.getByRole('button', { name: 'Не смогу присутствовать' }).click()
  await expect(page.getByText(/режим предварительного заявления включен/i)).toBeVisible()
  await page.getByRole('button', { name: 'Заявить заранее' }).click()
  await expect(page.getByText(/предварительная причина отсутствия отправлена/i)).toBeVisible()

  await page.getByRole('button', { name: 'QR' }).click()
  await page.getByRole('button', { name: 'Открыть сканер Telegram' }).click()
  await expect(page.getByText(/посещаемость отмечена: present/i)).toBeVisible()
  expect(lastQrToken).toBe('dynamic.jwt.token')

  await page.getByRole('button', { name: 'FAQ / Профиль' }).click()
  await expect(page.getByRole('main').getByText('Как привязать Telegram?', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Телефон')).toBeVisible()
  await assertNoRuntimeIssues()
})

test('teacher mini app opens QR, attendance and broadcast without runtime issues', async ({ page }) => {
  const assertNoRuntimeIssues = attachConsoleGuards(page)
  let correctionPosted = false
  let broadcastQueued = false

  await page.route('https://telegram.org/js/telegram-web-app.js?61', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: `
        window.Telegram = {
          WebApp: {
            initData: 'playwright-teacher-init-data',
            initDataUnsafe: {},
            version: '6.0',
            platform: 'unknown',
            colorScheme: 'light',
            isExpanded: true,
            viewportHeight: 720,
            viewportStableHeight: 720,
            themeParams: {},
            ready: function () {},
            expand: function () {},
            openTelegramLink: function () {}
          }
        };
      `,
    })
  })

  await page.route('**/tg/webapp/bootstrap', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
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
      }),
    })
  })

  await page.route('**/api/v1/teacher/lessons/lesson-1/attendance', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
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
      }),
    })
  })

  await page.route('**/api/v1/teacher/lessons', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
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
      ]),
    })
  })

  await page.route('**/api/v1/teacher/groups', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 'group-1', code: 'SE-101', name: 'SE-101' }]),
    })
  })

  await page.route('**/api/v1/teacher/absence-reasons', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.route('**/api/v1/teacher/qr/generate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        token: 'static-token',
        deeplink: 't.me/universe_bot?start=qr_static-token',
        expires_at: '2026-03-16T10:15:00Z',
      }),
    })
  })

  await page.route('**/api/v1/teacher/attendance/correct', async (route) => {
    correctionPosted = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'present' }),
    })
  })

  await page.route('**/api/v1/teacher/broadcasts**', async (route) => {
    broadcastQueued = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ recipients: 1 }),
    })
  })

  await page.route('**/api/v1/public/client-errors', async (route) => {
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'accepted' }),
    })
  })

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Test Teacher' })).toBeVisible()
  await expect(page.getByText('Universe Teacher')).toBeVisible()

  await page.getByRole('button', { name: 'Показать QR' }).click()
  await expect(page.getByText('https://t.me/universe_bot?start=qr_static-token')).toBeVisible()
  await expect(page.locator('.teacher-qr-box svg')).toBeVisible()

  await page.getByRole('button', { name: 'Отметки' }).click()
  await page.getByRole('button', { name: 'Открыть' }).click()
  await expect(page.getByText('Student One')).toBeVisible()
  await page.getByRole('combobox').nth(1).selectOption('present')
  await page.getByPlaceholder('Причина корректировки').fill('Manual check')
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect.poll(() => correctionPosted).toBe(true)

  await page.getByRole('button', { name: 'Рассылки' }).click()
  await page.getByRole('combobox').selectOption('group-1')
  await page.getByPlaceholder('Текст для студентов').fill('Проверьте обновление')
  await page.getByRole('button', { name: 'Отправить' }).click()
  await expect(page.getByText(/получателей: 1/i)).toBeVisible()
  expect(broadcastQueued).toBe(true)
  await assertNoRuntimeIssues()
})

test('student onboarding and pending approval states stay readable', async ({ page }) => {
  const assertNoRuntimeIssues = attachConsoleGuards(page)
  let bindingSubmitted = false

  await page.route('https://telegram.org/js/telegram-web-app.js?61', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: `
        window.Telegram = {
          WebApp: {
            initData: 'playwright-init-data',
            initDataUnsafe: {},
            version: '6.0',
            platform: 'unknown',
            colorScheme: 'light',
            isExpanded: true,
            viewportHeight: 720,
            viewportStableHeight: 720,
            themeParams: {},
            ready: function () {},
            expand: function () {}
          }
        };
      `,
    })
  })

  await page.route('**/tg/webapp/bootstrap', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        !bindingSubmitted
          ? { status: 'link_required' }
          : {
              status: 'pending',
              message: 'Binding request submitted',
              requested_full_name: 'Иванов Иван',
              group_code: 'SE-101',
              note: 'Переведен недавно',
              telegram_username: 'ivanov_student',
            },
      ),
    })
  })

  await page.route('**/tg/webapp/binding-request', async (route) => {
    bindingSubmitted = true
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'pending', message: 'Binding request submitted' }),
    })
  })

  await page.route('**/api/v1/public/client-errors', async (route) => {
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'accepted' }),
    })
  })

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Создание доступа' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Что подготовить' })).toBeVisible()

  await page.getByPlaceholder('Иванов Иван').fill('Иванов Иван')
  await page.getByPlaceholder('SE-101').fill('SE-101')
  await page.getByPlaceholder(/переведен недавно/i).fill('Переведен недавно')
  await page.getByRole('button', { name: 'Отправить заявку' }).click()

  await expect(page.getByRole('heading', { name: 'Заявка отправлена' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Что происходит дальше' })).toBeVisible()
  await expect(page.getByText('ivanov_student', { exact: true })).toBeVisible()
  await expect(page.getByText('SE-101').first()).toBeVisible()
  await expect(page.getByText('Binding request submitted', { exact: true }).first()).toBeVisible()
  await assertNoRuntimeIssues()
})
