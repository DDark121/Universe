import { useQuery } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'

type CategoryRow = {
  id: string
  name: string
  sort_order: number
  is_active: boolean
}

export function FaqCategoriesPage() {
  const query = useQuery({ queryKey: ['faq-categories'], queryFn: () => adminApi.listFaqCategories(true) })
  const statusQuery = useQuery({ queryKey: ['faq-status'], queryFn: () => adminApi.getFaqStatus() })

  if (query.isLoading || statusQuery.isLoading) return <Loader />
  if (query.isError) return <ErrorBlock message="Не удалось загрузить FAQ-категории" />
  if (statusQuery.isError) return <ErrorBlock message="Не удалось загрузить статус FAQ-индекса" />

  const status = statusQuery.data
  if (!status) return <Loader />
  const statusVariant =
    status.status === 'ready' ? 'success' : status.status === 'stale' || status.status === 'missing' ? 'warning' : 'default'

  return (
    <div className="page-grid">
      <PageTitle title="FAQ: категории" subtitle="Просмотр разделов базы знаний из markdown-файлов" />

      <Card>
        <h3>Read-only режим</h3>
        <p className="muted">FAQ больше не редактируется через админку. Источник правды: файлы `data/*.md`.</p>
        <div className="row">
          <Tag variant={statusVariant}>Статус индекса: {status.status}</Tag>
          <Tag variant={status.vector_runtime_available ? 'success' : 'warning'}>
            Векторный runtime: {status.vector_runtime_available ? 'доступен' : 'недоступен'}
          </Tag>
        </div>
        <p className="muted">
          Файлов: {status.file_count}. FAQ-элементов: {status.item_count}. Чанков: {status.chunk_count}. Собран:{' '}
          {status.built_at ? new Date(status.built_at).toLocaleString() : 'еще нет'}.
        </p>
        <p className="muted">Источник: {status.source_dir}</p>
      </Card>

      <Card>
        <Table
          rows={query.data ?? []}
          getRowKey={(row: CategoryRow) => row.id}
          columns={[
            { key: 'name', title: 'Название', render: (row: CategoryRow) => row.name },
            { key: 'sort_order', title: 'Порядок', render: (row: CategoryRow) => row.sort_order },
            {
              key: 'status',
              title: 'Статус',
              render: (row: CategoryRow) => <Tag variant={row.is_active ? 'success' : 'warning'}>{row.is_active ? 'Активна' : 'Отключена'}</Tag>,
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
