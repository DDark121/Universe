import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'

import { adminApi } from '@/shared/api/adminApi'
import type { RoleCode, UserItem } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'

type FormValues = {
  username: string
  full_name: string
  email: string
  phone_number: string
  role: RoleCode
}

export function UsersPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleCode | ''>('')
  const [groupFilter, setGroupFilter] = useState('')
  const [createdUser, setCreatedUser] = useState<{ username: string; temp_password: string } | null>(null)

  const usersQuery = useQuery({
    queryKey: ['users', search, roleFilter, groupFilter],
    queryFn: () =>
      adminApi.listUsers({
        ...(search ? { search } : {}),
        ...(roleFilter ? { role: roleFilter } : {}),
        ...(groupFilter ? { group_id: groupFilter } : {}),
      }),
  })
  const rolesQuery = useQuery({ queryKey: ['roles'], queryFn: () => adminApi.listRoles() })
  const groupsQuery = useQuery({ queryKey: ['groups-for-users'], queryFn: () => adminApi.listGroups() })

  const createMutation = useMutation({
    mutationFn: (payload: FormValues) =>
      adminApi.createUser({
        username: payload.username,
        full_name: payload.full_name,
        email: payload.email || undefined,
        phone_number: payload.phone_number,
        roles: [payload.role],
      }),
    onSuccess: (data) => {
      setCreatedUser({ username: data.username, temp_password: data.temp_password })
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      reset()
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      adminApi.updateUser(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const updateRolesMutation = useMutation({
    mutationFn: ({ id, roles }: { id: string; roles: RoleCode[] }) => adminApi.updateUserRoles(id, roles),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const { register, handleSubmit, reset } = useForm<FormValues>({
    defaultValues: {
      username: '',
      full_name: '',
      email: '',
      phone_number: '',
      role: 'student',
    },
  })

  const onSubmit = handleSubmit(async (payload) => {
    setCreatedUser(null)
    await createMutation.mutateAsync(payload)
  })

  const columns = useMemo(
    () => [
      {
        key: 'username',
        title: 'Логин',
        render: (row: UserItem) => row.username,
      },
      {
        key: 'name',
        title: 'ФИО',
        render: (row: UserItem) => row.full_name,
      },
      {
        key: 'email',
        title: 'Email',
        render: (row: UserItem) => row.email ?? '-',
      },
      {
        key: 'phone_number',
        title: 'Телефон',
        render: (row: UserItem) => row.phone_number ?? '-',
      },
      {
        key: 'roles',
        title: 'Роли',
        render: (row: UserItem) => row.roles.join(', '),
      },
      {
        key: 'status',
        title: 'Статус',
        render: (row: UserItem) => (row.is_archived ? 'Архив' : row.is_active ? 'Активен' : 'Отключен'),
      },
      {
        key: 'actions',
        title: 'Действия',
        render: (row: UserItem) => (
          <div className="row">
            <Button
              onClick={() =>
                updateMutation.mutate({
                  id: row.id,
                  payload: { is_active: !row.is_active },
                })
              }
            >
              {row.is_active ? 'Отключить' : 'Включить'}
            </Button>
            <Button
              onClick={() =>
                updateMutation.mutate({
                  id: row.id,
                  payload: { is_archived: !row.is_archived },
                })
              }
            >
              {row.is_archived ? 'Разархивировать' : 'В архив'}
            </Button>
            <Button
              onClick={() => {
                const nextRoles: RoleCode[] = row.roles.includes('curator')
                  ? row.roles.filter((item) => item !== 'curator')
                  : [...row.roles, 'curator']
                updateRolesMutation.mutate({ id: row.id, roles: nextRoles })
              }}
            >
              {row.roles.includes('curator') ? 'Снять тьютора' : 'Сделать тьютором'}
            </Button>
          </div>
        ),
      },
    ],
    [updateMutation, updateRolesMutation],
  )

  if (usersQuery.isLoading || rolesQuery.isLoading || groupsQuery.isLoading) {
    return <Loader />
  }

  const loadError = usersQuery.error ?? rolesQuery.error ?? groupsQuery.error

  if (loadError) {
    return (
      <div className="page-grid">
        <PageTitle title="Пользователи" subtitle="CRUD пользователей и управление ролями" />
        <ErrorBlock message={getApiErrorMessage(loadError, 'Не удалось загрузить пользователей')} />
      </div>
    )
  }

  return (
    <div className="page-grid">
      <PageTitle title="Пользователи" subtitle="CRUD пользователей и управление ролями" />

      <Card>
        <h3>Фильтры</h3>
        <div className="form-grid">
          <Input
            placeholder="Поиск по имени/логину/email/телефону"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value as RoleCode | '')}>
            <option value="">Все роли</option>
            {rolesQuery.data?.map((role) => (
              <option key={role.id} value={role.code}>
                {role.name}
              </option>
            ))}
          </Select>
          <Select value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}>
            <option value="">Все группы</option>
            {groupsQuery.data?.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <Card>
        <h3>Создать пользователя</h3>
        <form className="form-grid" onSubmit={onSubmit}>
          <Input placeholder="username" {...register('username', { required: true })} />
          <Input placeholder="ФИО" {...register('full_name', { required: true })} />
          <Input placeholder="Email" {...register('email')} />
          <Input placeholder="Телефон" {...register('phone_number', { required: true })} />
          <Select {...register('role')}>
            <option value="student">student</option>
            <option value="teacher">teacher</option>
            <option value="admin">admin</option>
            <option value="curator">тьютор</option>
          </Select>
          <Button variant="primary" type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Создаем...' : 'Создать'}
          </Button>
        </form>
        {createdUser ? (
          <p className="muted">
            Пользователь <strong>{createdUser.username}</strong> создан. Временный пароль: <code>{createdUser.temp_password}</code>
          </p>
        ) : null}
        {createMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(createMutation.error, 'Не удалось создать пользователя')} />
        ) : null}
      </Card>

      <Card>
        <h3>Список пользователей</h3>
        <Table columns={columns} rows={usersQuery.data ?? []} getRowKey={(row) => row.id} />
      </Card>
    </div>
  )
}
