import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { teacherApi } from '@/shared/api/teacherApi'
import type { TeacherLessonAttendanceResponse } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDateTime, humanizeStatus } from '@/shared/utils/format'
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

const STATUS_OPTIONS = [
  { value: 'present', label: 'Присутствовал' },
  { value: 'late', label: 'Опоздал' },
  { value: 'absent', label: 'Отсутствовал' },
]

function statusVariant(status: string | null) {
  if (status === 'present') return 'success' as const
  if (status === 'late') return 'warning' as const
  if (status === 'absent') return 'danger' as const
  return 'default' as const
}

export function TeacherAttendancePage() {
  const { lessonId } = useParams<{ lessonId: string }>()
  const queryClient = useQueryClient()
  const toast = useToast()

  const [statusDrafts, setStatusDrafts] = useState<Record<string, 'present' | 'late' | 'absent'>>({})
  const [reasonDrafts, setReasonDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['teacher-lesson-attendance', lessonId],
    queryFn: () => teacherApi.getLessonAttendance(lessonId ?? ''),
    enabled: Boolean(lessonId),
  })

  const correctionMutation = useMutation({
    mutationFn: (payload: {
      lesson_id: string
      student_id: string
      status: 'present' | 'late' | 'absent'
      reason: string
    }) => teacherApi.correctAttendance(payload),
    onSuccess: async (_data, variables) => {
      setReasonDrafts((previous) => ({ ...previous, [variables.student_id]: '' }))
      setStatusDrafts((previous) => {
        const next = { ...previous }
        delete next[variables.student_id]
        return next
      })
      await queryClient.invalidateQueries({ queryKey: ['teacher-lesson-attendance', lessonId] })
      toast.push('Корректировка сохранена', 'success')
    },
    onError: (mutationError) => {
      setError(getApiErrorMessage(mutationError, 'Не удалось сохранить корректировку'))
    },
  })

  const lesson = useMemo(() => query.data?.lesson ?? null, [query.data])

  if (!lessonId) {
    return <ErrorBlock message="Некорректный ID занятия" />
  }

  if (query.isLoading) {
    return <Loader />
  }

  if (query.isError || !query.data) {
    return <ErrorBlock message={getApiErrorMessage(query.error, 'Не удалось загрузить отметки')} />
  }

  return (
    <div className="page-grid">
      <PageTitle
        title={`Отметки: ${lesson?.discipline_name ?? '-'}`}
        subtitle={`${lesson?.group_code ?? '-'} • ${lesson?.group_name ?? '-'} • ${formatDateTime(lesson?.starts_at)}`}
        actions={
          <Link className="link-btn" to="/teacher/lessons">
            Вернуться к занятиям
          </Link>
        }
      />

      {error ? <ErrorBlock message={error} /> : null}

      <Card>
        <Table
          rows={query.data.students}
          getRowKey={(row) => row.student_id}
          columns={[
            {
              key: 'student',
              title: 'Студент',
              render: (row: TeacherLessonAttendanceResponse['students'][number]) => (
                <div className="stack">
                  <span>{row.full_name}</span>
                  <span className="muted-small">@{row.username}</span>
                </div>
              ),
            },
            {
              key: 'current',
              title: 'Текущий статус',
              render: (row: TeacherLessonAttendanceResponse['students'][number]) => (
                <div className="stack">
                  <Tag variant={statusVariant(row.status)}>{humanizeStatus(row.status)}</Tag>
                  <span className="muted-small">{formatDateTime(row.marked_at)}</span>
                  <span className="muted-small">{row.source ? `Источник: ${humanizeStatus(row.source)}` : '-'}</span>
                </div>
              ),
            },
            {
              key: 'excused',
              title: 'Уважительность',
              render: (row: TeacherLessonAttendanceResponse['students'][number]) => (
                <Tag variant={row.is_excused ? 'success' : 'default'}>{row.is_excused ? 'Уваж.' : 'Не отмечено'}</Tag>
              ),
            },
            {
              key: 'draft',
              title: 'Новый статус',
              render: (row: TeacherLessonAttendanceResponse['students'][number]) => (
                <Select
                  value={statusDrafts[row.student_id] ?? row.status ?? ''}
                  onChange={(event) => {
                    setStatusDrafts((previous) => ({
                      ...previous,
                      [row.student_id]: event.target.value as 'present' | 'late' | 'absent',
                    }))
                  }}
                >
                  <option value="">Выберите статус</option>
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              ),
            },
            {
              key: 'reason',
              title: 'Причина корректировки',
              render: (row: TeacherLessonAttendanceResponse['students'][number]) => (
                <Input
                  value={reasonDrafts[row.student_id] ?? ''}
                  placeholder="Обязательная причина"
                  onChange={(event) => {
                    setReasonDrafts((previous) => ({
                      ...previous,
                      [row.student_id]: event.target.value,
                    }))
                  }}
                />
              ),
            },
            {
              key: 'actions',
              title: 'Сохранение',
              render: (row: TeacherLessonAttendanceResponse['students'][number]) => (
                <Button
                  variant="primary"
                  disabled={correctionMutation.isPending}
                  onClick={() => {
                    const nextStatus = statusDrafts[row.student_id] ?? row.status
                    const reason = (reasonDrafts[row.student_id] ?? '').trim()
                    if (!nextStatus) {
                      setError('Выберите новый статус')
                      return
                    }
                    if (!reason) {
                      setError('Укажите причину корректировки')
                      return
                    }
                    setError(null)
                    correctionMutation.mutate({
                      lesson_id: lessonId,
                      student_id: row.student_id,
                      status: nextStatus,
                      reason,
                    })
                  }}
                >
                  Сохранить
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
