import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

function paged<T>(items: T[]) {
  return {
    items,
    meta: {
      page: 1,
      page_size: Math.max(items.length, 1),
      total_items: items.length,
      total_pages: 1,
    },
  }
}

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

test('login page renders', async ({ page }) => {
  const assertNoRuntimeIssues = attachConsoleGuards(page)
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Вход в админ-панель' })).toBeVisible()
  await expect(page.getByPlaceholder('admin')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible()
  await assertNoRuntimeIssues()
})

test('admin login opens dashboard, import center, and faq list without UI regressions', async ({ page }) => {
  const assertNoRuntimeIssues = attachConsoleGuards(page)
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = `${url.pathname}${url.search}`

    if (path.endsWith('/auth/login') && request.method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'access-token',
          refresh_token: 'refresh-token',
          token_type: 'bearer',
          access_expires_at: '2026-03-31T00:00:00Z',
          refresh_expires_at: '2026-04-14T00:00:00Z',
          password_change_required: false,
        }),
      })
      return
    }

    if (path.endsWith('/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'admin-1',
          username: 'admin',
          email: 'admin@example.local',
          phone_number: '+70000000000',
          full_name: 'UI Admin',
          roles: ['admin'],
          is_active: true,
          must_change_password: false,
        }),
      })
      return
    }

    if (path.includes('/admin/users')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          paged([
            {
              id: 'user-1',
              username: 'student_1',
              email: 'student_1@example.local',
              phone_number: '+77010000001',
              full_name: 'Student One',
              roles: ['student'],
              is_active: true,
              is_archived: false,
            },
          ]),
        ),
      })
      return
    }

    if (path.includes('/admin/groups')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          paged([
            {
              id: 'group-1',
              code: 'SE-101',
              name: 'SE-101',
              faculty_id: 'faculty-1',
              stream_id: 'stream-1',
              is_archived: false,
            },
          ]),
        ),
      })
      return
    }

    if (path.includes('/admin/disciplines')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          paged([
            {
              id: 'discipline-1',
              code: 'DB',
              name: 'Databases',
              is_archived: false,
            },
          ]),
        ),
      })
      return
    }

    if (path.includes('/admin/risk/students')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          paged([
            {
              student_id: 'student-1',
              student_name: 'Student One',
              group_name: 'SE-101',
              score: 58,
              late_count: 2,
              unexcused_absence_count: 1,
              reasons: { attendance: 'watch' },
            },
          ]),
        ),
      })
      return
    }

    if (path.includes('/admin/reports/attendance')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          present: 18,
          late: 3,
          absent: 2,
          excused_absent: 1,
          unexcused_absent: 1,
        }),
      })
      return
    }

    if (path.includes('/admin/reports/lates')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          paged([
            {
              attendance_id: 'late-1',
              lesson_id: 'lesson-1',
              student_id: 'student-1',
              student_name: 'Student One',
              marked_at: '2026-03-31T09:11:00Z',
              starts_at: '2026-03-31T09:00:00Z',
              group_id: 'group-1',
              discipline_id: 'discipline-1',
              teacher_id: 'teacher-1',
            },
          ]),
        ),
      })
      return
    }

    if (path.includes('/admin/imports')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
      return
    }

    if (path.includes('/admin/ai-imports')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
      return
    }

    if (path.includes('/admin/faq/categories')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          paged([
            {
              id: 'category-1',
              name: 'Регистрация',
              sort_order: 100,
              is_active: true,
            },
          ]),
        ),
      })
      return
    }

    if (path.includes('/admin/faq/status')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ready',
          assistant_enabled: true,
          model_name: 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
          file_count: 20,
          item_count: 20,
          built_at: '2026-03-31T00:00:00Z',
        }),
      })
      return
    }

    if (path.includes('/admin/faq/items')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          paged([
            {
              id: 'faq-1',
              category_id: 'category-1',
              question: 'Как привязать Telegram?',
              answer: 'Откройте mini app и отправьте заявку.',
              keywords: 'telegram',
              is_active: true,
            },
          ]),
        ),
      })
      return
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: `Unhandled mock for ${path}` }),
    })
  })

  await page.goto('/login')
  await page.getByPlaceholder('Введите пароль').fill('Admin123!')
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page.getByRole('heading', { name: 'Панель управления' })).toBeVisible()
  await expect(page.getByText('UI Admin')).toBeVisible()
  await expect(page.getByText('Студенты в риске')).toBeVisible()

  await page.getByRole('link', { name: 'Импорт' }).click()
  await expect(page.getByRole('heading', { name: 'Импорт', exact: true })).toBeVisible()
  await expect(page.getByText('Классический импорт')).toBeVisible()
  await expect(page.getByText('AI Import Wizard')).toBeVisible()
  await expect(page.getByText('Файл классического импорта')).toBeVisible()

  await page.getByRole('link', { name: 'FAQ вопросы' }).click()
  await expect(page.getByRole('heading', { name: 'FAQ: вопросы' })).toBeVisible()
  await expect(page.getByText(/статус индекса: ready/i)).toBeVisible()
  await expect(page.getByText('Как привязать Telegram?')).toBeVisible()
  await assertNoRuntimeIssues()
})

test('teacher login generates a visible QR code for a lesson', async ({ page }) => {
  const assertNoRuntimeIssues = attachConsoleGuards(page)
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = `${url.pathname}${url.search}`

    if (path.endsWith('/auth/login') && request.method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'teacher-access-token',
          refresh_token: 'teacher-refresh-token',
          token_type: 'bearer',
          access_expires_at: '2026-03-31T00:00:00Z',
          refresh_expires_at: '2026-04-14T00:00:00Z',
          password_change_required: false,
        }),
      })
      return
    }

    if (path.endsWith('/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'teacher-1',
          username: 'teacher',
          email: 'teacher@example.local',
          phone_number: '+77010000010',
          full_name: 'QR Teacher',
          roles: ['teacher'],
          is_active: true,
          must_change_password: false,
        }),
      })
      return
    }

    if (path.includes('/teacher/lessons')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'lesson-1',
            group_id: 'group-1',
            group_code: 'SE-301',
            group_name: 'SE-301',
            discipline_id: 'discipline-1',
            discipline_code: 'DB',
            discipline_name: 'Databases',
            starts_at: '2026-03-31T09:00:00Z',
            ends_at: '2026-03-31T10:30:00Z',
            status: 'in_progress',
            room: 'A-101',
          },
        ]),
      })
      return
    }

    if (path.endsWith('/teacher/qr/generate') && request.method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'static-token-1',
          deeplink: 'https://t.me/universe_test_bot?start=qr_static-token-1',
          expires_at: '2026-03-31T10:15:00Z',
        }),
      })
      return
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: `Unhandled mock for ${path}` }),
    })
  })

  await page.goto('/login')
  await page.getByPlaceholder('Введите пароль').fill('Teacher123!')
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page.getByRole('heading', { name: 'Мои занятия' })).toBeVisible()
  await expect(page.getByText('QR Teacher')).toBeVisible()

  await page.getByRole('button', { name: 'Показать QR' }).click()

  await expect(page.getByRole('heading', { name: 'Статический QR' })).toBeVisible()
  await expect(page.getByText('https://t.me/universe_test_bot?start=qr_static-token-1')).toBeVisible()
  await expect(page.locator('.teacher-qr-box svg')).toBeVisible()
  await assertNoRuntimeIssues()
})
