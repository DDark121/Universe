import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { useDebouncedValue } from '@/shared/utils/debounce'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'

type FaqItemRow = {
  id: string
  category_id: string
  question: string
  answer: string
  keywords: string
  is_active: boolean
}

export function FaqItemsPage() {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 350)

  const categoriesQuery = useQuery({ queryKey: ['faq-categories-select'], queryFn: () => adminApi.listFaqCategories(true) })
  const statusQuery = useQuery({ queryKey: ['faq-status'], queryFn: () => adminApi.getFaqStatus() })
  const itemsQuery = useQuery({
    queryKey: ['faq-items', debouncedSearch],
    queryFn: () => adminApi.listFaqItems(debouncedSearch || undefined, true),
  })

  if (categoriesQuery.isLoading || itemsQuery.isLoading || statusQuery.isLoading) {
    return <Loader />
  }
  if (categoriesQuery.isError) return <ErrorBlock message="Не удалось загрузить FAQ-категории" />
  if (itemsQuery.isError) return <ErrorBlock message="Не удалось загрузить FAQ-вопросы" />
  if (statusQuery.isError) return <ErrorBlock message="Не удалось загрузить статус FAQ-индекса" />

  const status = statusQuery.data
  if (!status) return <Loader />
  const statusVariant =
    status.status === 'ready' ? 'success' : status.status === 'stale' || status.status === 'missing' ? 'warning' : 'default'

  return (
    <div className="page-grid">
      <PageTitle
        title="FAQ: вопросы"
        subtitle="Поиск и просмотр вопросов из markdown-файлов"
        actions={<Input placeholder="Поиск" value={search} onChange={(e) => setSearch(e.target.value)} />}
      />

      <Card>
        <h3>Read-only режим</h3>
        <p className="muted">Изменяйте FAQ-файлы в директории `data/*.md`, затем вручную пересоберите FAISS-индекс.</p>
        <div className="row">
          <Tag variant={statusVariant}>Статус индекса: {status.status}</Tag>
          <Tag variant={status.assistant_enabled ? 'success' : 'warning'}>
            FAQ assistant: {status.assistant_enabled ? 'включен' : 'выключен'}
          </Tag>
        </div>
        <p className="muted">
          Модель: {status.model_name}. Файлов: {status.file_count}. FAQ-элементов: {status.item_count}. Собран:{' '}
          {status.built_at ? new Date(status.built_at).toLocaleString() : 'еще нет'}.
        </p>
      </Card>

      <Card>
        <Table
          rows={itemsQuery.data ?? []}
          getRowKey={(row: FaqItemRow) => row.id}
          columns={[
            {
              key: 'category',
              title: 'Категория',
              render: (row: FaqItemRow) =>
                categoriesQuery.data?.find((category) => category.id === row.category_id)?.name ?? row.category_id,
            },
            { key: 'question', title: 'Вопрос', render: (row: FaqItemRow) => row.question },
            { key: 'keywords', title: 'Ключи', render: (row: FaqItemRow) => row.keywords || '-' },
            {
              key: 'status',
              title: 'Статус',
              render: (row: FaqItemRow) => <Tag variant={row.is_active ? 'success' : 'warning'}>{row.is_active ? 'Активен' : 'Отключен'}</Tag>,
            },
            {
              key: 'actions',
              title: 'Действия',
              render: () => <span className="muted">Редактируется через `data/*.md`</span>,
            },
          ]}
        />
      </Card>
    </div>
  )
}
