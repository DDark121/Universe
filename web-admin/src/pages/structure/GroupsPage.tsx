import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'

import { adminApi } from '@/shared/api/adminApi'
import type { GroupItem } from '@/shared/api/types'
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
  code: string
  name: string
  faculty_id?: string
  stream_id?: string
  is_subgroup: string
  window_start_offset_override_minutes?: string
  window_duration_override_minutes?: string
  late_threshold_override_minutes?: string
  telegram_chat_id?: string
  telegram_chat_title?: string
}

function toNullableNumber(value?: string) {
  if (!value?.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function GroupsPage() {
  const queryClient = useQueryClient()
  const groupsQuery = useQuery({ queryKey: ['groups'], queryFn: () => adminApi.listGroups() })
  const facultiesQuery = useQuery({ queryKey: ['groups-faculties'], queryFn: () => adminApi.listFaculties() })
  const streamsQuery = useQuery({ queryKey: ['groups-streams'], queryFn: () => adminApi.listStreams() })

  const { register, handleSubmit, reset } = useForm<FormValues>({
    defaultValues: {
      code: '',
      name: '',
      faculty_id: '',
      stream_id: '',
      is_subgroup: 'false',
      window_start_offset_override_minutes: '',
      window_duration_override_minutes: '',
      late_threshold_override_minutes: '',
      telegram_chat_id: '',
      telegram_chat_title: '',
    },
  })

  const createMutation = useMutation({
    mutationFn: (payload: FormValues) =>
      adminApi.createGroup({
        code: payload.code,
        name: payload.name,
        faculty_id: payload.faculty_id || null,
        stream_id: payload.stream_id || null,
        is_subgroup: payload.is_subgroup === 'true',
        window_start_offset_override_minutes: toNullableNumber(payload.window_start_offset_override_minutes),
        window_duration_override_minutes: toNullableNumber(payload.window_duration_override_minutes),
        late_threshold_override_minutes: toNullableNumber(payload.late_threshold_override_minutes),
        telegram_chat_id: toNullableNumber(payload.telegram_chat_id),
        telegram_chat_title: payload.telegram_chat_title || null,
      }),
    onSuccess: () => {
      reset()
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      adminApi.updateGroup(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
    },
  })

  const columns = useMemo(
    () => [
      { key: 'code', title: 'Код', render: (row: GroupItem) => row.code },
      { key: 'name', title: 'Название', render: (row: GroupItem) => row.name },
      {
        key: 'faculty',
        title: 'Факультет',
        render: (row: GroupItem) =>
          facultiesQuery.data?.find((faculty) => faculty.id === row.faculty_id)?.name ?? '-',
      },
      {
        key: 'stream',
        title: 'Поток',
        render: (row: GroupItem) => streamsQuery.data?.find((stream) => stream.id === row.stream_id)?.name ?? '-',
      },
      {
        key: 'attendance',
        title: 'Окно / Опоздание',
        render: (row: GroupItem) =>
          [
            row.window_start_offset_override_minutes != null ? `старт ${row.window_start_offset_override_minutes}` : null,
            row.window_duration_override_minutes != null ? `окно ${row.window_duration_override_minutes}` : null,
            row.late_threshold_override_minutes != null ? `late ${row.late_threshold_override_minutes}` : null,
          ]
            .filter(Boolean)
            .join(' · ') || '-',
      },
      {
        key: 'telegram',
        title: 'Telegram чат',
        render: (row: GroupItem) => row.telegram_chat_title || row.telegram_chat_id || '-',
      },
      {
        key: 'archived',
        title: 'Архив',
        render: (row: GroupItem) => (row.is_archived ? 'Да' : 'Нет'),
      },
      {
        key: 'actions',
        title: 'Действия',
        render: (row: GroupItem) => (
          <div className="row">
            <Button
              onClick={() => {
                const nextName = window.prompt('Название группы', row.name)
                if (!nextName) return
                const telegramChatId = window.prompt(
                  'Telegram chat id (пусто чтобы очистить)',
                  row.telegram_chat_id ? String(row.telegram_chat_id) : '',
                )
                const telegramChatTitle = window.prompt(
                  'Telegram chat title',
                  row.telegram_chat_title || '',
                )
                const windowStart = window.prompt(
                  'Старт окна отметки, минут',
                  row.window_start_offset_override_minutes != null
                    ? String(row.window_start_offset_override_minutes)
                    : '',
                )
                const windowDuration = window.prompt(
                  'Длительность окна, минут',
                  row.window_duration_override_minutes != null
                    ? String(row.window_duration_override_minutes)
                    : '',
                )
                const lateThreshold = window.prompt(
                  'Порог опоздания, минут',
                  row.late_threshold_override_minutes != null
                    ? String(row.late_threshold_override_minutes)
                    : '',
                )
                updateMutation.mutate({
                  id: row.id,
                  payload: {
                    name: nextName,
                    telegram_chat_id: toNullableNumber(telegramChatId || ''),
                    telegram_chat_title: telegramChatTitle || null,
                    window_start_offset_override_minutes: toNullableNumber(windowStart || ''),
                    window_duration_override_minutes: toNullableNumber(windowDuration || ''),
                    late_threshold_override_minutes: toNullableNumber(lateThreshold || ''),
                  },
                })
              }}
            >
              Настроить
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
    ],
    [facultiesQuery.data, streamsQuery.data, updateMutation],
  )

  if (groupsQuery.isLoading || facultiesQuery.isLoading || streamsQuery.isLoading) return <Loader />

  const loadError = groupsQuery.error ?? facultiesQuery.error ?? streamsQuery.error

  if (loadError) {
    return (
      <div className="page-grid">
        <PageTitle title="Группы и подгруппы" subtitle="Структура академических групп" />
        <ErrorBlock message={getApiErrorMessage(loadError, 'Не удалось загрузить структуру групп')} />
      </div>
    )
  }

  return (
    <div className="page-grid">
      <PageTitle title="Группы и подгруппы" subtitle="Структура академических групп" />

      <Card>
        <h3>Новая группа</h3>
        <form className="form-grid" onSubmit={handleSubmit((payload) => createMutation.mutate(payload))}>
          <Input placeholder="Код" {...register('code', { required: true })} />
          <Input placeholder="Название" {...register('name', { required: true })} />
          <Select {...register('faculty_id')}>
            <option value="">Факультет (опционально)</option>
            {facultiesQuery.data?.map((faculty) => (
              <option key={faculty.id} value={faculty.id}>
                {faculty.name}
              </option>
            ))}
          </Select>
          <Select {...register('stream_id')}>
            <option value="">Поток (опционально)</option>
            {streamsQuery.data?.map((stream) => (
              <option key={stream.id} value={stream.id}>
                {stream.name}
              </option>
            ))}
          </Select>
          <Select {...register('is_subgroup')}>
            <option value="false">Обычная группа</option>
            <option value="true">Подгруппа</option>
          </Select>
          <Input
            placeholder="Старт окна отметки, минут"
            {...register('window_start_offset_override_minutes')}
          />
          <Input
            placeholder="Длительность окна, минут"
            {...register('window_duration_override_minutes')}
          />
          <Input
            placeholder="Порог опоздания, минут"
            {...register('late_threshold_override_minutes')}
          />
          <Input placeholder="Telegram chat id" {...register('telegram_chat_id')} />
          <Input placeholder="Telegram chat title" {...register('telegram_chat_title')} />
          <Button variant="primary" type="submit">
            Добавить
          </Button>
        </form>
        {createMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(createMutation.error, 'Не удалось создать группу')} />
        ) : null}
        {updateMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(updateMutation.error, 'Не удалось обновить группу')} />
        ) : null}
      </Card>

      <Card>
        <Table columns={columns} rows={groupsQuery.data ?? []} getRowKey={(row) => row.id} />
      </Card>
    </div>
  )
}
