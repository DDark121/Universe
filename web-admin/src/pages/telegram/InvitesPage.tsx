import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useForm } from 'react-hook-form'

import { adminApi } from '@/shared/api/adminApi'
import type { InviteCodeItem } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDateTime } from '@/shared/utils/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

type FormValues = {
  role_code: 'student' | 'teacher' | 'admin' | 'curator'
  expires_at: string
  max_activations: number
  group_id: string
  discipline_id: string
}

export function InvitesPage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const invitesQuery = useQuery({ queryKey: ['invite-codes'], queryFn: () => adminApi.listInviteCodes() })
  const groupsQuery = useQuery({ queryKey: ['invite-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({ queryKey: ['invite-disciplines'], queryFn: () => adminApi.listDisciplines() })

  const form = useForm<FormValues>({
    defaultValues: {
      role_code: 'student',
      expires_at: dayjs().add(7, 'day').hour(23).minute(59).format('YYYY-MM-DDTHH:mm'),
      max_activations: 1,
      group_id: '',
      discipline_id: '',
    },
  })

  const createMutation = useMutation({
    mutationFn: (payload: FormValues) =>
      adminApi.createInvite({
        role_code: payload.role_code,
        expires_at: dayjs(payload.expires_at).toISOString(),
        max_activations: Number(payload.max_activations),
        group_id: payload.group_id || null,
        discipline_id: payload.discipline_id || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['invite-codes'] })
      toast.push('Инвайт-код создан', 'success')
    },
  })

  const onSubmit = form.handleSubmit(async (payload) => {
    await createMutation.mutateAsync(payload)
  })

  if (invitesQuery.isLoading || groupsQuery.isLoading || disciplinesQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle title="Invite-коды Telegram" subtitle="Выдача кодов для привязки аккаунтов" />

      <Card>
        <h3>Создать invite-код</h3>
        <form className="form-grid" onSubmit={onSubmit}>
          <Select {...form.register('role_code')}>
            <option value="student">Студент</option>
            <option value="teacher">Преподаватель</option>
            <option value="curator">Куратор</option>
            <option value="admin">Администратор</option>
          </Select>
          <label>
            Срок действия
            <input className="input" type="datetime-local" {...form.register('expires_at', { required: true })} />
          </label>
          <label>
            Макс. активаций
            <input
              className="input"
              type="number"
              min={1}
              max={1000}
              {...form.register('max_activations', { valueAsNumber: true, required: true })}
            />
          </label>
          <Select {...form.register('group_id')}>
            <option value="">Группа (опц.)</option>
            {groupsQuery.data?.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </Select>
          <Select {...form.register('discipline_id')}>
            <option value="">Дисциплина (опц.)</option>
            {disciplinesQuery.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Button variant="primary" type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Создаем...' : 'Создать код'}
          </Button>
        </form>
        {createMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(createMutation.error, 'Не удалось создать invite-код')} />
        ) : null}
      </Card>

      <Card>
        <Table
          rows={invitesQuery.data ?? []}
          getRowKey={(row: InviteCodeItem) => row.id ?? row.code}
          columns={[
            {
              key: 'code',
              title: 'Код',
              render: (row: InviteCodeItem) => <code className="code">{row.code}</code>,
            },
            {
              key: 'role',
              title: 'Роль',
              render: (row: InviteCodeItem) => row.role_code ?? '-',
            },
            {
              key: 'expires',
              title: 'Действует до',
              render: (row: InviteCodeItem) => formatDateTime(row.expires_at),
            },
            {
              key: 'limits',
              title: 'Активации',
              render: (row: InviteCodeItem) => (
                <span className="mono">
                  {row.activation_count ?? 0}/{row.max_activations}
                </span>
              ),
            },
            {
              key: 'active',
              title: 'Статус',
              render: (row: InviteCodeItem) => (
                <Tag variant={row.is_active ? 'success' : 'warning'}>{row.is_active ? 'Активен' : 'Отключен'}</Tag>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
