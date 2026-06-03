import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'

type TutorAssignment = {
  id: string
  tutor_user_id: string
  group_id: string
  is_active: boolean
  created_at: string
}

export function TutorAssignmentsPage() {
  const queryClient = useQueryClient()
  const [tutorUserId, setTutorUserId] = useState('')
  const [groupId, setGroupId] = useState('')

  const assignmentsQuery = useQuery({
    queryKey: ['tutor-assignments'],
    queryFn: () => adminApi.listTutorAssignments() as Promise<TutorAssignment[]>,
  })
  const tutorsQuery = useQuery({
    queryKey: ['tutor-users'],
    queryFn: () => adminApi.listUsers({ role: 'curator' }),
  })
  const groupsQuery = useQuery({
    queryKey: ['tutor-groups-admin'],
    queryFn: () => adminApi.listGroups(),
  })

  const createMutation = useMutation({
    mutationFn: () => adminApi.createTutorAssignment({ tutor_user_id: tutorUserId, group_id: groupId }),
    onSuccess: () => {
      setTutorUserId('')
      setGroupId('')
      void queryClient.invalidateQueries({ queryKey: ['tutor-assignments'] })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      adminApi.updateTutorAssignment(id, { is_active }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tutor-assignments'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminApi.deleteTutorAssignment(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tutor-assignments'] }),
  })

  const tutorsMap = useMemo(
    () => new Map((tutorsQuery.data ?? []).map((user) => [user.id, user.full_name])),
    [tutorsQuery.data],
  )
  const groupsMap = useMemo(
    () => new Map((groupsQuery.data ?? []).map((group) => [group.id, group.name])),
    [groupsQuery.data],
  )

  if (assignmentsQuery.isLoading || tutorsQuery.isLoading || groupsQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle
        title="Назначения тьюторов"
        subtitle="Привязка тьюторов (role=curator) к группам"
      />

      <Card>
        <div className="form-grid">
          <Select value={tutorUserId} onChange={(e) => setTutorUserId(e.target.value)}>
            <option value="">Выберите тьютора</option>
            {tutorsQuery.data?.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name}
              </option>
            ))}
          </Select>
          <Select value={groupId} onChange={(e) => setGroupId(e.target.value)}>
            <option value="">Выберите группу</option>
            {groupsQuery.data?.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </Select>
          <Button
            variant="primary"
            disabled={!tutorUserId || !groupId || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? 'Добавление...' : 'Добавить'}
          </Button>
        </div>
        {createMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(createMutation.error, 'Не удалось создать назначение')} />
        ) : null}
      </Card>

      <Card>
        <Table
          rows={(assignmentsQuery.data ?? []) as TutorAssignment[]}
          getRowKey={(row) => row.id}
          columns={[
            {
              key: 'tutor',
              title: 'Тьютор',
              render: (row) => tutorsMap.get(row.tutor_user_id) ?? row.tutor_user_id,
            },
            {
              key: 'group',
              title: 'Группа',
              render: (row) => groupsMap.get(row.group_id) ?? row.group_id,
            },
            { key: 'active', title: 'Статус', render: (row) => (row.is_active ? 'Активно' : 'Неактивно') },
            {
              key: 'actions',
              title: 'Действия',
              render: (row) => (
                <div className="row">
                  <Button
                    onClick={() =>
                      toggleMutation.mutate({ id: row.id, is_active: !row.is_active })
                    }
                  >
                    {row.is_active ? 'Деактивировать' : 'Активировать'}
                  </Button>
                  <Button variant="danger" onClick={() => deleteMutation.mutate(row.id)}>
                    Удалить
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
