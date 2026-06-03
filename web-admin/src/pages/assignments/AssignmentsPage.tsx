import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'

import { adminApi } from '@/shared/api/adminApi'
import type { AssignmentItem } from '@/shared/api/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'

type FormValues = {
  teacher_id: string
  discipline_id: string
  group_id: string
}

export function AssignmentsPage() {
  const queryClient = useQueryClient()

  const assignmentsQuery = useQuery({ queryKey: ['assignments'], queryFn: () => adminApi.listAssignments() })
  const usersQuery = useQuery({ queryKey: ['assignment-users'], queryFn: () => adminApi.listUsers() })
  const groupsQuery = useQuery({ queryKey: ['assignment-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({
    queryKey: ['assignment-disciplines'],
    queryFn: () => adminApi.listDisciplines(),
  })

  const { register, handleSubmit, reset } = useForm<FormValues>()

  const createMutation = useMutation({
    mutationFn: (payload: FormValues) => adminApi.createAssignment(payload),
    onSuccess: () => {
      reset()
      void queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      adminApi.updateAssignment(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })

  const archiveMutation = useMutation({
    mutationFn: (id: string) => adminApi.archiveAssignment(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })

  if (assignmentsQuery.isLoading || usersQuery.isLoading || groupsQuery.isLoading || disciplinesQuery.isLoading) {
    return <Loader />
  }

  const teachers = (usersQuery.data ?? []).filter((user) => user.roles.includes('teacher'))

  return (
    <div className="page-grid">
      <PageTitle title="Назначения преподавателей" subtitle="Связь преподаватель-дисциплина-группа" />

      <Card>
        <h3>Новое назначение</h3>
        <form className="form-grid" onSubmit={handleSubmit((payload) => createMutation.mutate(payload))}>
          <Select {...register('teacher_id', { required: true })}>
            <option value="">Преподаватель</option>
            {teachers.map((teacher) => (
              <option key={teacher.id} value={teacher.id}>
                {teacher.full_name}
              </option>
            ))}
          </Select>
          <Select {...register('discipline_id', { required: true })}>
            <option value="">Дисциплина</option>
            {disciplinesQuery.data?.map((discipline) => (
              <option key={discipline.id} value={discipline.id}>
                {discipline.name}
              </option>
            ))}
          </Select>
          <Select {...register('group_id', { required: true })}>
            <option value="">Группа</option>
            {groupsQuery.data?.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </Select>
          <Button variant="primary" type="submit">
            Добавить
          </Button>
        </form>
      </Card>

      <Card>
        <Table
          rows={assignmentsQuery.data ?? []}
          getRowKey={(row) => row.id}
          columns={[
            {
              key: 'teacher',
              title: 'Преподаватель',
              render: (row: AssignmentItem) =>
                usersQuery.data?.find((user) => user.id === row.teacher_id)?.full_name ?? row.teacher_id,
            },
            {
              key: 'discipline',
              title: 'Дисциплина',
              render: (row: AssignmentItem) =>
                disciplinesQuery.data?.find((discipline) => discipline.id === row.discipline_id)?.name ?? row.discipline_id,
            },
            {
              key: 'group',
              title: 'Группа',
              render: (row: AssignmentItem) =>
                groupsQuery.data?.find((group) => group.id === row.group_id)?.name ?? row.group_id,
            },
            { key: 'active', title: 'Активно', render: (row: AssignmentItem) => (row.is_active ? 'Да' : 'Нет') },
            {
              key: 'actions',
              title: 'Действия',
              render: (row: AssignmentItem) => (
                <div className="row">
                  <Button
                    onClick={() =>
                      updateMutation.mutate({ id: row.id, payload: { is_active: !row.is_active } })
                    }
                  >
                    {row.is_active ? 'Отключить' : 'Включить'}
                  </Button>
                  <Button variant="danger" onClick={() => archiveMutation.mutate(row.id)}>
                    Архив
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
