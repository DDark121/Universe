import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useForm } from 'react-hook-form'

import { adminApi } from '@/shared/api/adminApi'
import type { LessonItem, UserItem } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDateTime } from '@/shared/utils/format'
import { ActionChip } from '@/shared/ui/ActionChip'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { FilePickerPanel } from '@/shared/ui/FilePickerPanel'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

type LessonFormValues = {
  group_id: string
  discipline_id: string
  teacher_id: string
  starts_at: string
  ends_at: string
  room: string
}

const STATUS_OPTIONS = [
  { value: 'planned', label: 'Запланировано' },
  { value: 'in_progress', label: 'Идет' },
  { value: 'completed', label: 'Завершено' },
  { value: 'canceled', label: 'Отменено' },
  { value: 'rescheduled', label: 'Перенесено' },
]

function statusVariant(status: string) {
  if (status === 'completed') return 'success' as const
  if (status === 'canceled') return 'danger' as const
  if (status === 'rescheduled') return 'warning' as const
  return 'default' as const
}

export function SchedulePage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [dateFrom, setDateFrom] = useState(dayjs().startOf('month').format('YYYY-MM-DD'))
  const [dateTo, setDateTo] = useState(dayjs().endOf('month').format('YYYY-MM-DD'))
  const [statusUpdates, setStatusUpdates] = useState<Record<string, string>>({})
  const [statusReason, setStatusReason] = useState<Record<string, string>>({})
  const [importFile, setImportFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  const lessonsQuery = useQuery({
    queryKey: ['lessons', dateFrom, dateTo],
    queryFn: () => adminApi.listLessons({ date_from: dateFrom, date_to: dateTo }),
  })
  const groupsQuery = useQuery({ queryKey: ['schedule-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({ queryKey: ['schedule-disciplines'], queryFn: () => adminApi.listDisciplines() })
  const usersQuery = useQuery({ queryKey: ['schedule-users'], queryFn: () => adminApi.listUsers({ role: 'teacher' }) })

  const teachers = useMemo(
    () => (usersQuery.data ?? []).filter((user: UserItem) => user.roles.includes('teacher')),
    [usersQuery.data],
  )

  const createMutation = useMutation({
    mutationFn: (payload: LessonFormValues) =>
      adminApi.createLesson({
        group_id: payload.group_id,
        discipline_id: payload.discipline_id,
        teacher_id: payload.teacher_id,
        starts_at: dayjs(payload.starts_at).toISOString(),
        ends_at: dayjs(payload.ends_at).toISOString(),
        room: payload.room || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lessons'] })
      toast.push('Занятие создано', 'success')
    },
    onError: (e) => setError(getApiErrorMessage(e, 'Не удалось создать занятие')),
  })

  const updateStatusMutation = useMutation({
    mutationFn: ({ lessonId, status }: { lessonId: string; status: string }) =>
      adminApi.updateLessonStatus(lessonId, {
        status,
        canceled_reason: statusReason[lessonId] || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lessons'] })
      toast.push('Статус занятия обновлен', 'success')
    },
    onError: (e) => setError(getApiErrorMessage(e, 'Не удалось обновить статус')),
  })

  const importMutation = useMutation({
    mutationFn: (file: File) => adminApi.importLessons(file),
    onSuccess: () => {
      setImportFile(null)
      toast.push('Импорт расписания запущен', 'success')
    },
    onError: (e) => setError(getApiErrorMessage(e, 'Не удалось запустить импорт')),
  })

  const form = useForm<LessonFormValues>({
    defaultValues: {
      group_id: '',
      discipline_id: '',
      teacher_id: '',
      starts_at: dayjs().add(1, 'day').hour(9).minute(0).format('YYYY-MM-DDTHH:mm'),
      ends_at: dayjs().add(1, 'day').hour(10).minute(30).format('YYYY-MM-DDTHH:mm'),
      room: '',
    },
  })

  const onCreate = form.handleSubmit(async (payload) => {
    setError(null)
    await createMutation.mutateAsync(payload)
    form.reset({
      ...payload,
      room: '',
    })
  })

  if (lessonsQuery.isLoading || groupsQuery.isLoading || disciplinesQuery.isLoading || usersQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle
        title="Расписание"
        subtitle="Управление занятиями, статусами и импортом CSV/XLSX"
        actions={
          <div className="row">
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
        }
      />

      <div className="split-grid stagger-list">
        <Card>
          <h3>Создать занятие</h3>
          <form className="form-grid" onSubmit={onCreate}>
            <Select {...form.register('group_id', { required: true })}>
              <option value="">Группа</option>
              {groupsQuery.data?.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </Select>
            <Select {...form.register('discipline_id', { required: true })}>
              <option value="">Дисциплина</option>
              {disciplinesQuery.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </Select>
            <Select {...form.register('teacher_id', { required: true })}>
              <option value="">Преподаватель</option>
              {teachers.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>
                  {teacher.full_name}
                </option>
              ))}
            </Select>
            <label>
              Начало
              <Input type="datetime-local" {...form.register('starts_at', { required: true })} />
            </label>
            <label>
              Конец
              <Input type="datetime-local" {...form.register('ends_at', { required: true })} />
            </label>
            <Input placeholder="Аудитория" {...form.register('room')} />
            <Button variant="primary" type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Сохраняем...' : 'Создать'}
            </Button>
          </form>
        </Card>

        <Card>
          <div className="control-stack">
            <div className="panel-header">
              <div>
                <div className="panel-kicker">Schedule Import</div>
                <h3>Импорт расписания</h3>
                <p className="muted">Загрузите CSV/XLSX, backend создаст async job.</p>
              </div>
            </div>

            <div className="summary-grid">
              <div className="summary-tile">
                <span className="summary-label">Форматы</span>
                <span className="summary-value">CSV / XLSX</span>
              </div>
              <div className="summary-tile">
                <span className="summary-label">Обработка</span>
                <span className="summary-value">Фоновая задача</span>
              </div>
            </div>

            <FilePickerPanel
              accept=".csv,.xlsx"
              badge="Upload"
              description="Файл уйдет в асинхронный импорт, а итог можно будет проверить по списку занятий."
              file={importFile}
              label="Файл расписания"
              onFileChange={setImportFile}
            />

            <div className="toolbar-line">
              <span className="muted-small">
                {importFile ? `К запуску выбран ${importFile.name}` : 'Подготовьте CSV/XLSX с корректными колонками расписания.'}
              </span>
              <div className="toolbar-actions">
                <ActionChip
                  variant="primary"
                  onClick={() => {
                    if (importFile) importMutation.mutate(importFile)
                  }}
                  disabled={!importFile || importMutation.isPending}
                >
                  {importMutation.isPending ? 'Запуск...' : 'Запустить импорт'}
                </ActionChip>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {error ? <ErrorBlock message={error} /> : null}

      <Card>
        <Table
          rows={lessonsQuery.data ?? []}
          getRowKey={(row: LessonItem) => row.id}
          columns={[
            {
              key: 'time',
              title: 'Время',
              render: (row: LessonItem) => (
                <div className="stack">
                  <span>{formatDateTime(row.starts_at)}</span>
                  <span className="muted-small">до {formatDateTime(row.ends_at)}</span>
                </div>
              ),
            },
            {
              key: 'group',
              title: 'Группа',
              render: (row: LessonItem) => groupsQuery.data?.find((item) => item.id === row.group_id)?.name ?? row.group_id,
            },
            {
              key: 'discipline',
              title: 'Дисциплина',
              render: (row: LessonItem) =>
                disciplinesQuery.data?.find((item) => item.id === row.discipline_id)?.name ?? row.discipline_id,
            },
            {
              key: 'teacher',
              title: 'Преподаватель',
              render: (row: LessonItem) => teachers.find((item) => item.id === row.teacher_id)?.full_name ?? row.teacher_id,
            },
            {
              key: 'status',
              title: 'Статус',
              render: (row: LessonItem) => <Tag variant={statusVariant(row.status)}>{row.status}</Tag>,
            },
            {
              key: 'actions',
              title: 'Изменение статуса',
              render: (row: LessonItem) => (
                <div className="stack">
                  <Select
                    value={statusUpdates[row.id] ?? row.status}
                    onChange={(e) => {
                      setStatusUpdates((prev) => ({ ...prev, [row.id]: e.target.value }))
                    }}
                  >
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                  <Input
                    placeholder="Причина (для отмены/переноса)"
                    value={statusReason[row.id] ?? ''}
                    onChange={(e) => {
                      setStatusReason((prev) => ({ ...prev, [row.id]: e.target.value }))
                    }}
                  />
                  <Button
                    onClick={() =>
                      updateStatusMutation.mutate({
                        lessonId: row.id,
                        status: statusUpdates[row.id] ?? row.status,
                      })
                    }
                    disabled={updateStatusMutation.isPending}
                  >
                    Сохранить
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
