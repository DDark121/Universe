import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Table } from '@/shared/ui/Table'

export function FacultiesPage() {
  const queryClient = useQueryClient()
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  const query = useQuery({ queryKey: ['faculties'], queryFn: () => adminApi.listFaculties() })
  const createMutation = useMutation({
    mutationFn: () => adminApi.createFaculty({ code, name }),
    onSuccess: () => {
      setCode('')
      setName('')
      void queryClient.invalidateQueries({ queryKey: ['faculties'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { code?: string; name?: string } }) =>
      adminApi.updateFaculty(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['faculties'] })
    },
  })

  if (query.isLoading) return <Loader />

  return (
    <div className="page-grid">
      <PageTitle title="Факультеты" subtitle="Управление справочником факультетов" />

      <Card>
        <h3>Новый факультет</h3>
        <div className="form-grid">
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Код" />
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название" />
          <Button variant="primary" onClick={() => createMutation.mutate()} disabled={!code || !name}>
            Добавить
          </Button>
        </div>
      </Card>

      <Card>
        <Table
          rows={query.data ?? []}
          getRowKey={(row) => row.id}
          columns={[
            { key: 'code', title: 'Код', render: (row) => row.code },
            { key: 'name', title: 'Название', render: (row) => row.name },
            {
              key: 'actions',
              title: 'Действия',
              render: (row) => (
                <Button
                  onClick={() => {
                    const nextName = prompt('Новое название факультета', row.name)
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
