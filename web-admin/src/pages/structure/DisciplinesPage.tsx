import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import type { DisciplineItem } from '@/shared/api/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Table } from '@/shared/ui/Table'

export function DisciplinesPage() {
  const queryClient = useQueryClient()
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [windowStartOffsetOverrideMinutes, setWindowStartOffsetOverrideMinutes] = useState('')
  const [windowDurationOverrideMinutes, setWindowDurationOverrideMinutes] = useState('')
  const [lateThresholdOverrideMinutes, setLateThresholdOverrideMinutes] = useState('')

  const query = useQuery({ queryKey: ['disciplines'], queryFn: () => adminApi.listDisciplines() })

  const createMutation = useMutation({
    mutationFn: () =>
      adminApi.createDiscipline({
        code,
        name,
        window_start_offset_override_minutes: windowStartOffsetOverrideMinutes
          ? Number(windowStartOffsetOverrideMinutes)
          : null,
        window_duration_override_minutes: windowDurationOverrideMinutes ? Number(windowDurationOverrideMinutes) : null,
        late_threshold_override_minutes: lateThresholdOverrideMinutes ? Number(lateThresholdOverrideMinutes) : null,
      }),
    onSuccess: () => {
      setCode('')
      setName('')
      setWindowStartOffsetOverrideMinutes('')
      setWindowDurationOverrideMinutes('')
      setLateThresholdOverrideMinutes('')
      void queryClient.invalidateQueries({ queryKey: ['disciplines'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      adminApi.updateDiscipline(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['disciplines'] })
    },
  })

  if (query.isLoading) return <Loader />

  return (
    <div className="page-grid">
      <PageTitle title="Дисциплины" subtitle="Справочник дисциплин и архивирование" />

      <Card>
        <h3>Новая дисциплина</h3>
        <div className="form-grid">
          <Input placeholder="Код" value={code} onChange={(e) => setCode(e.target.value)} />
          <Input placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} />
          <Input
            placeholder="Старт окна отметки, минут"
            value={windowStartOffsetOverrideMinutes}
            onChange={(e) => setWindowStartOffsetOverrideMinutes(e.target.value)}
          />
          <Input
            placeholder="Длительность окна, минут"
            value={windowDurationOverrideMinutes}
            onChange={(e) => setWindowDurationOverrideMinutes(e.target.value)}
          />
          <Input
            placeholder="Порог опоздания, минут"
            value={lateThresholdOverrideMinutes}
            onChange={(e) => setLateThresholdOverrideMinutes(e.target.value)}
          />
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
            { key: 'code', title: 'Код', render: (row: DisciplineItem) => row.code },
            { key: 'name', title: 'Название', render: (row: DisciplineItem) => row.name },
            {
              key: 'attendance',
              title: 'Окно / Опоздание',
              render: (row: DisciplineItem) =>
                [
                  row.window_start_offset_override_minutes != null
                    ? `старт ${row.window_start_offset_override_minutes}`
                    : null,
                  row.window_duration_override_minutes != null ? `окно ${row.window_duration_override_minutes}` : null,
                  row.late_threshold_override_minutes != null ? `late ${row.late_threshold_override_minutes}` : null,
                ]
                  .filter(Boolean)
                  .join(' · ') || '-',
            },
            {
              key: 'status',
              title: 'Статус',
              render: (row: DisciplineItem) => (row.is_archived ? 'Архив' : 'Активна'),
            },
            {
              key: 'actions',
              title: 'Действия',
              render: (row: DisciplineItem) => (
                <div className="row">
                  <Button
                    onClick={() => {
                      const nextName = prompt('Новое название дисциплины', row.name)
                      const nextWindowStart = prompt(
                        'Старт окна отметки, минут',
                        row.window_start_offset_override_minutes != null
                          ? String(row.window_start_offset_override_minutes)
                          : '',
                      )
                      const nextWindowDuration = prompt(
                        'Длительность окна, минут',
                        row.window_duration_override_minutes != null
                          ? String(row.window_duration_override_minutes)
                          : '',
                      )
                      const nextLateThreshold = prompt(
                        'Порог опоздания, минут',
                        row.late_threshold_override_minutes != null
                          ? String(row.late_threshold_override_minutes)
                          : '',
                      )
                      if (nextName) {
                        updateMutation.mutate({
                          id: row.id,
                          payload: {
                            name: nextName,
                            window_start_offset_override_minutes: nextWindowStart ? Number(nextWindowStart) : null,
                            window_duration_override_minutes: nextWindowDuration ? Number(nextWindowDuration) : null,
                            late_threshold_override_minutes: nextLateThreshold ? Number(nextLateThreshold) : null,
                          },
                        })
                      }
                    }}
                  >
                    Изменить
                  </Button>
                  <Button
                    onClick={() =>
                      updateMutation.mutate({
                        id: row.id,
                        payload: { is_archived: !row.is_archived },
                      })
                    }
                  >
                    {row.is_archived ? 'Разархивировать' : 'Архивировать'}
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
