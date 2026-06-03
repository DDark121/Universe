import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import type { BindingRequestItem } from '@/shared/api/types'
import { useDebouncedValue } from '@/shared/utils/debounce'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDateTime } from '@/shared/utils/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

function statusVariant(status: string) {
  if (status === 'approved') return 'success' as const
  if (status === 'rejected') return 'danger' as const
  return 'warning' as const
}

export function BindingRequestsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [selection, setSelection] = useState<Record<string, string>>({})
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 300)

  const requestsQuery = useQuery({
    queryKey: ['binding-requests'],
    queryFn: () => adminApi.listBindingRequests(),
  })
  const usersQuery = useQuery({
    queryKey: ['binding-users', debouncedSearch],
    queryFn: () =>
      adminApi.listUsers({
        page_size: 30,
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
      }),
  })

  const decisionMutation = useMutation({
    mutationFn: (payload: { request_id: string; user_id: string; approve: boolean }) => adminApi.decideBinding(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['binding-requests'] })
      toast.push('Решение сохранено', 'success')
    },
  })

  if (requestsQuery.isLoading || (usersQuery.isLoading && !usersQuery.data)) {
    return <Loader />
  }

  const requests = requestsQuery.data ?? []
  const fallbackUserId = usersQuery.data?.[0]?.id ?? ''

  return (
    <div className="page-grid">
      <PageTitle title="Ручные привязки Telegram" subtitle="Одобрение заявок на привязку Telegram ID" />

      {requestsQuery.isError ? (
        <ErrorBlock message={getApiErrorMessage(requestsQuery.error, 'Не удалось загрузить список заявок Telegram')} />
      ) : null}

      {usersQuery.isError ? (
        <ErrorBlock message={getApiErrorMessage(usersQuery.error, 'Не удалось загрузить список пользователей для привязки')} />
      ) : null}

      {decisionMutation.isError ? (
        <ErrorBlock message={getApiErrorMessage(decisionMutation.error, 'Не удалось обработать заявку')} />
      ) : null}

      <Card>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
          <div>
            <strong>Поиск пользователя для привязки</strong>
            <p className="muted" style={{ margin: '6px 0 0' }}>
              Ищите по ФИО, логину или email. В списке ниже показываются только найденные пользователи.
            </p>
          </div>
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск пользователя"
            style={{ maxWidth: 320 }}
          />
        </div>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <p className="muted" style={{ margin: 0 }}>
            Заявок загружено: {requests.length}
          </p>
          <Button
            variant="secondary"
            onClick={() => {
              void queryClient.invalidateQueries({ queryKey: ['binding-requests'] })
              void queryClient.invalidateQueries({ queryKey: ['binding-users'] })
            }}
          >
            Обновить
          </Button>
        </div>
      </Card>

      {!requestsQuery.isError && requests.length === 0 ? (
        <Card>
          <p style={{ margin: 0 }}>Заявок пока нет. Если mini app только что отправила заявку, нажмите «Обновить».</p>
        </Card>
      ) : null}

      <Card>
        <Table
          rows={requests}
          getRowKey={(row: BindingRequestItem) => row.id}
          columns={[
            {
              key: 'id',
              title: 'ID заявки',
              render: (row: BindingRequestItem) => <span className="mono">{row.id}</span>,
            },
            {
              key: 'telegram',
              title: 'Telegram',
              render: (row: BindingRequestItem) => (
                <div>
                  <div className="mono">{row.telegram_id}</div>
                  <div className="muted">{row.telegram_username || 'username не указан'}</div>
                </div>
              ),
            },
            {
              key: 'created_at',
              title: 'Создана',
              render: (row: BindingRequestItem) => (
                <div>
                  <div>{formatDateTime(row.created_at)}</div>
                  <div className="muted">{row.resolved_at ? `Решена: ${formatDateTime(row.resolved_at)}` : 'Ожидает решения'}</div>
                </div>
              ),
            },
            {
              key: 'status',
              title: 'Статус',
              render: (row: BindingRequestItem) => <Tag variant={statusVariant(row.status)}>{row.status}</Tag>,
            },
            {
              key: 'request',
              title: 'Заявка',
              render: (row: BindingRequestItem) => (
                <div>
                  <div>{row.full_name || 'ФИО не указано'}</div>
                  <div className="muted">Группа: {row.group_code || 'не указана'}</div>
                  <div className="muted">{row.note || 'Без комментария'}</div>
                </div>
              ),
            },
            {
              key: 'requested_user',
              title: 'Пользователь',
              render: (row: BindingRequestItem) => (
                <Select
                  value={selection[row.id] ?? row.requested_user_id ?? ''}
                  disabled={row.status !== 'pending'}
                  onChange={(e) => setSelection((prev) => ({ ...prev, [row.id]: e.target.value }))}
                >
                  <option value="">Выберите пользователя</option>
                  {usersQuery.data?.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name} ({user.username})
                    </option>
                  ))}
                </Select>
              ),
            },
            {
              key: 'actions',
              title: 'Решение',
              render: (row: BindingRequestItem) => (
                <div className="row">
                  <Button
                    variant="primary"
                    disabled={row.status !== 'pending' || !selection[row.id] || decisionMutation.isPending}
                    onClick={() => {
                      const userId = selection[row.id]
                      if (!userId) return
                      decisionMutation.mutate({
                        request_id: row.id,
                        user_id: userId,
                        approve: true,
                      })
                    }}
                  >
                    Одобрить
                  </Button>
                  <Button
                    variant="danger"
                    disabled={
                      row.status !== 'pending' ||
                      decisionMutation.isPending ||
                      !(selection[row.id] || row.requested_user_id || fallbackUserId)
                    }
                    onClick={() => {
                      decisionMutation.mutate({
                        request_id: row.id,
                        user_id: selection[row.id] || row.requested_user_id || fallbackUserId,
                        approve: false,
                      })
                    }}
                  >
                    Отклонить
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
