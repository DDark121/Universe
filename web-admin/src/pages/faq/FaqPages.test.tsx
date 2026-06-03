import type { ReactElement } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'

const { listFaqCategories, listFaqItems, getFaqStatus } = vi.hoisted(() => ({
  listFaqCategories: vi.fn(),
  listFaqItems: vi.fn(),
  getFaqStatus: vi.fn(),
}))

vi.mock('@/shared/api/adminApi', () => ({
  adminApi: {
    listFaqCategories,
    listFaqItems,
    getFaqStatus,
  },
}))

import { FaqCategoriesPage } from '@/pages/faq/FaqCategoriesPage'
import { FaqItemsPage } from '@/pages/faq/FaqItemsPage'

function renderWithQuery(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  listFaqCategories.mockResolvedValue([
    { id: 'cat-1', name: 'general', sort_order: 100, is_active: true },
  ])
  listFaqItems.mockResolvedValue([
    {
      id: 'faq-1',
      category_id: 'cat-1',
      question: 'telegram-binding',
      answer: 'Откройте mini app и отправьте заявку.',
      keywords: '',
      is_active: true,
    },
  ])
  getFaqStatus.mockResolvedValue({
    status: 'ready',
    assistant_enabled: true,
    vector_runtime_available: true,
    source_dir: '/app/data',
    source_hash: 'source-hash',
    index_hash: 'index-hash',
    file_count: 1,
    item_count: 1,
    chunk_count: 1,
    built_at: '2026-03-30T17:20:00Z',
    model_name: 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
  })
})

it('renders faq categories page in read-only mode', async () => {
  renderWithQuery(<FaqCategoriesPage />)

  expect(await screen.findByText(/read-only режим/i)).toBeInTheDocument()
  expect(screen.getByText(/источник правды: файлы `data\/\*\.md`/i)).toBeInTheDocument()
  expect(screen.getByText(/статус индекса: ready/i)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /добавить/i })).not.toBeInTheDocument()
  expect(screen.getByText(/редактируется через `data\/\*\.md`/i)).toBeInTheDocument()
})

it('renders faq items page in read-only mode', async () => {
  renderWithQuery(<FaqItemsPage />)

  expect(await screen.findByText(/read-only режим/i)).toBeInTheDocument()
  expect(screen.getByText(/изменяйте faq-файлы в директории `data\/\*\.md`/i)).toBeInTheDocument()
  expect(screen.getByText(/статус индекса: ready/i)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /добавить/i })).not.toBeInTheDocument()
  expect(screen.getByText(/редактируется через `data\/\*\.md`/i)).toBeInTheDocument()
})
