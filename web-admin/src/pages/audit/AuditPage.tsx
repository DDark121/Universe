import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { ActionChip } from '@/shared/ui/ActionChip'
import { useDebouncedValue } from '@/shared/utils/debounce'
import { downloadCsv } from '@/shared/utils/csv'
import { formatDateTime } from '@/shared/utils/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'

export function AuditPage() {
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  const debouncedAction = useDebouncedValue(action, 350)

  const usersQuery = useQuery({ queryKey: ['audit-users'], queryFn: () => adminApi.listUsers() })
  const auditQuery = useQuery({
    queryKey: ['audit-logs', debouncedAction, actor, dateFrom, dateTo, page, pageSize],
    queryFn: () =>
      adminApi.listAudit({
        ...(debouncedAction ? { action: debouncedAction } : {}),
        ...(actor ? { actor } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
        page: String(page),
        page_size: String(pageSize),
      }),
  })

  if (usersQuery.isLoading || auditQuery.isLoading) {
    return <Loader />
  }

  const total = auditQuery.data?.meta.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="page-grid">
      <PageTitle
        title="Аудит лог"
        subtitle="Критичные действия, фильтрация и постраничный просмотр"
        actions={
          <ActionChip
            variant="secondary"
            onClick={() => {
              downloadCsv(
                `audit_page_${page}.csv`,
                (auditQuery.data?.items ?? []).map((item) => ({
                  id: item.id,
                  created_at: item.created_at,
                  actor_user_id: item.actor_user_id,
                  action: item.action,
                  entity_type: item.entity_type,
                  entity_id: item.entity_id,
                  details: JSON.stringify(item.details ?? {}),
                })),
              )
            }}
          >
            Скачать CSV страницы
          </ActionChip>
        }
      />

      <Card>
        <div className="form-grid">
          <Input placeholder="action (например admin.user_update)" value={action} onChange={(e) => setAction(e.target.value)} />
          <Select
            value={actor}
            onChange={(e) => {
              setActor(e.target.value)
              setPage(1)
            }}
          >
            <option value="">Любой пользователь</option>
            {usersQuery.data?.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name}
              </option>
            ))}
          </Select>
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          <Select
            value={String(pageSize)}
            onChange={(e) => {
              const next = Number(e.target.value)
              setPageSize(next)
              setPage(1)
            }}
          >
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="200">200</option>
          </Select>
        </div>
      </Card>

      <Card>
        <Table
          rows={auditQuery.data?.items ?? []}
          getRowKey={(row) => row.id}
          columns={[
            { key: 'created_at', title: 'Время', render: (row) => formatDateTime(row.created_at) },
            {
              key: 'actor',
              title: 'Кто',
              render: (row) => usersQuery.data?.find((user) => user.id === row.actor_user_id)?.full_name ?? row.actor_user_id ?? '-',
            },
            { key: 'action', title: 'Действие', render: (row) => row.action },
            { key: 'entity_type', title: 'Сущность', render: (row) => row.entity_type },
            { key: 'entity_id', title: 'Entity ID', render: (row) => row.entity_id ?? '-' },
            {
              key: 'details',
              title: 'Payload',
              render: (row) => (
                <code className="code" style={{ maxWidth: 420, display: 'inline-block', overflowWrap: 'anywhere' }}>
                  {JSON.stringify(row.details ?? {})}
                </code>
              ),
            },
          ]}
        />

        <div className="space-between" style={{ marginTop: 12 }}>
          <div className="muted-small">
            Страница {page} из {totalPages}, всего записей: {total}
          </div>
          <div className="row">
            <Button
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page <= 1}
            >
              Назад
            </Button>
            <Button
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={page >= totalPages}
            >
              Вперед
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
