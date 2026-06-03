import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const adminApi = vi.hoisted(() => ({
  applyAIImport: vi.fn(),
  createAIImportDraft: vi.fn(),
  getAIImport: vi.fn(),
  listAIImports: vi.fn(),
  listDisciplines: vi.fn(),
  listFaculties: vi.fn(),
  listGroups: vi.fn(),
  listImports: vi.fn(),
  listStreams: vi.fn(),
  listUsers: vi.fn(),
  rejectAIImport: vi.fn(),
  updateAIImport: vi.fn(),
  uploadImport: vi.fn(),
  createImportJob: vi.fn(),
  downloadImportErrors: vi.fn(),
}))

vi.mock('@/shared/api/adminApi', () => ({
  adminApi,
}))

import { AiImportDraftPage } from '@/pages/imports/AiImportDraftPage'
import { ImportsPage } from '@/pages/imports/ImportsPage'
import { ToastProvider } from '@/shared/ui/ToastProvider'

function renderWithProviders(ui: ReactNode, initialEntries: string[] = ['/imports']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  Object.values(adminApi).forEach((mockFn) => mockFn.mockReset())
  adminApi.listImports.mockResolvedValue([])
  adminApi.listAIImports.mockResolvedValue([])
  adminApi.listFaculties.mockResolvedValue([])
  adminApi.listStreams.mockResolvedValue([])
  adminApi.listGroups.mockResolvedValue([])
  adminApi.listDisciplines.mockResolvedValue([])
  adminApi.listUsers.mockResolvedValue([])
  adminApi.applyAIImport.mockResolvedValue({})
  adminApi.rejectAIImport.mockResolvedValue({})
})

it('requires calendar fields for schedule-like AI imports and allows users-only draft creation without them', async () => {
  const file = new File(['users'], 'users.docx', {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })

  renderWithProviders(<ImportsPage />)
  await screen.findByRole('heading', { name: 'AI Import Wizard' })

  const aiModeSelect = screen.getByLabelText('Режим AI-импорта')
  const aiFileInput = screen.getByLabelText('Файл AI-импорта')
  const submitButton = screen.getByRole('button', { name: 'Создать AI draft' })

  fireEvent.change(aiFileInput, { target: { files: [file] } })
  expect(submitButton).toBeDisabled()

  fireEvent.change(aiModeSelect, { target: { value: 'users' } })
  expect(submitButton).toBeEnabled()

  adminApi.createAIImportDraft.mockResolvedValue({ id: 'draft-1' })
  fireEvent.click(submitButton)

  await waitFor(() => {
    expect(adminApi.createAIImportDraft).toHaveBeenCalledWith({
      file,
      mode: 'users',
      wizard: {
        term_start: null,
        term_end: null,
        first_week_parity: null,
      },
    })
  })
})

it('loads AI draft preview and persists wizard edits back to the API', async () => {
  const draft = {
    id: 'draft-1',
    status: 'draft',
    mode: 'mixed',
    file_name: 'schedule.docx',
    created_at: '2026-03-30T08:00:00Z',
    updated_at: '2026-03-30T09:00:00Z',
    completed_at: null,
    summary: {
      detected_doc_kind: 'mixed',
      confidence: 0.83,
      counts: { issues: 1, lessons: 0 },
      source_metadata: null,
      excerpt: 'Schedule excerpt',
    },
    wizard: {
      term_start: '2026-09-01',
      term_end: '2026-12-20',
      first_week_parity: 'odd',
    },
    payload: {
      detected_doc_kind: 'mixed',
      notes: [],
      entities: {
        faculties: [],
        streams: [],
        groups: [],
        disciplines: [],
        users: [],
        memberships: [],
        assignments: [],
      },
      schedule_patterns: [],
      lessons: [],
    },
    issues: [
      {
        severity: 'error',
        code: 'ambiguous_teacher',
        message: 'Resolve teacher manually',
        source_ref: 'page-1',
        field_path: 'entities.users.0',
        requires_action: true,
      },
    ],
    apply_result: null,
    error_report: null,
  }

  adminApi.getAIImport.mockResolvedValue(draft)
  adminApi.updateAIImport.mockImplementation(async (_draftId: string, payload: Record<string, unknown>) => ({
    ...draft,
    ...payload,
  }))

  const { container } = renderWithProviders(
    <Routes>
      <Route path="/imports/ai/:draftId" element={<AiImportDraftPage />} />
    </Routes>,
    ['/imports/ai/draft-1'],
  )

  expect(await screen.findByText('schedule.docx')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Проблемы (1)' })).toBeInTheDocument()

  const dateInputs = container.querySelectorAll('input[type="date"]')
  fireEvent.change(dateInputs[0]!, { target: { value: '2026-09-08' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить draft' }))

  await waitFor(() => {
    expect(adminApi.updateAIImport).toHaveBeenCalledWith(
      'draft-1',
      expect.objectContaining({
        wizard: expect.objectContaining({
          term_start: '2026-09-08',
          term_end: '2026-12-20',
          first_week_parity: 'odd',
        }),
        payload: expect.objectContaining({
          detected_doc_kind: 'mixed',
        }),
      }),
    )
  })
})
