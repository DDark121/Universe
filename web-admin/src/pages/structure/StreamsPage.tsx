import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'

export function StreamsPage() {
  const queryClient = useQueryClient()
  const facultiesQuery = useQuery({ queryKey: ['faculties-streams'], queryFn: () => adminApi.listFaculties() })
  const streamsQuery = useQuery({ queryKey: ['streams'], queryFn: () => adminApi.listStreams() })

  const [facultyId, setFacultyId] = useState('')
  const [name, setName] = useState('')

  const createMutation = useMutation({
    mutationFn: () => adminApi.createStream({ faculty_id: facultyId, name }),
    onSuccess: () => {
      setFacultyId('')
      setName('')
      void queryClient.invalidateQueries({ queryKey: ['streams'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { name?: string; faculty_id?: string } }) =>
      adminApi.updateStream(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['streams'] })
    },
  })

  if (streamsQuery.isLoading || facultiesQuery.isLoading) return <Loader />

  return (
    <div className="page-grid">
      <PageTitle title="Потоки" subtitle="Потоки и привязка к факультетам" />

      <Card>
        <h3>Новый поток</h3>
        <div className="form-grid">
          <Select value={facultyId} onChange={(e) => setFacultyId(e.target.value)}>
            <option value="">Выберите факультет</option>
            {facultiesQuery.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название потока" />
          <Button variant="primary" onClick={() => createMutation.mutate()} disabled={!facultyId || !name}>
            Добавить
          </Button>
        </div>
      </Card>

      <Card>
        <Table
          rows={streamsQuery.data ?? []}
          getRowKey={(row) => row.id}
          columns={[
            {
              key: 'faculty',
              title: 'Факультет',
              render: (row) => facultiesQuery.data?.find((item) => item.id === row.faculty_id)?.name ?? row.faculty_id,
            },
            { key: 'name', title: 'Название', render: (row) => row.name },
            {
              key: 'actions',
              title: 'Действия',
              render: (row) => (
                <Button
                  onClick={() => {
                    const nextName = prompt('Новое имя потока', row.name)
                    if (nextName) {
                      updateMutation.mutate({ id: row.id, payload: { name: nextName } })
                    }
                  }}
                >
                  Изменить
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
