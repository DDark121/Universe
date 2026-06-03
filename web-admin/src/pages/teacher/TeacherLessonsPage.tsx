import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import QRCode from 'react-qr-code'
import { Link, useNavigate } from 'react-router-dom'

import { teacherApi } from '@/shared/api/teacherApi'
import type { TeacherLessonItem, TeacherQrGenerateResponse } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDateTime, humanizeStatus } from '@/shared/utils/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

function lessonStatusVariant(status: string) {
  if (status === 'completed') return 'success' as const
  if (status === 'canceled') return 'danger' as const
  if (status === 'rescheduled') return 'warning' as const
  return 'default' as const
}

function qrStatusVariant(expiresAt: string) {
  const diffMinutes = dayjs(expiresAt).diff(dayjs(), 'minute')
  if (diffMinutes <= 0) return 'danger' as const
  if (diffMinutes <= 5) return 'warning' as const
  return 'success' as const
}

export function TeacherLessonsPage() {
  const navigate = useNavigate()
  const toast = useToast()

  const [dateFrom, setDateFrom] = useState(dayjs().startOf('month').format('YYYY-MM-DD'))
  const [dateTo, setDateTo] = useState(dayjs().endOf('month').format('YYYY-MM-DD'))
  const [selectedQrLesson, setSelectedQrLesson] = useState<TeacherLessonItem | null>(null)
  const [staticQr, setStaticQr] = useState<TeacherQrGenerateResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const lessonsQuery = useQuery({
    queryKey: ['teacher-lessons', dateFrom, dateTo],
    queryFn: () => teacherApi.listLessons({ date_from: dateFrom, date_to: dateTo }),
  })

  const staticQrMutation = useMutation({
    mutationFn: (lessonId: string) => teacherApi.generateQr(lessonId),
    onSuccess: (data, lessonId) => {
      const lesson = lessonsQuery.data?.find((item) => item.id === lessonId) ?? null
      setSelectedQrLesson(lesson)
      setStaticQr(data)
      toast.push('Статический QR сгенерирован', 'success')
    },
    onError: (mutationError) => {
      setError(getApiErrorMessage(mutationError, 'Не удалось сгенерировать QR'))
    },
  })

  const dynamicMutation = useMutation({
    mutationFn: (lessonId: string) => teacherApi.startDynamicQrSession(lessonId),
    onSuccess: (data) => {
      toast.push('Динамическая QR-сессия запущена', 'success')
      navigate(`/teacher/qr-sessions/${data.session_id}`)
    },
    onError: (mutationError) => {
      setError(getApiErrorMessage(mutationError, 'Не удалось запустить динамический QR'))
    },
  })

  if (lessonsQuery.isLoading) {
    return <Loader />
  }

  if (lessonsQuery.isError) {
    return <ErrorBlock message={getApiErrorMessage(lessonsQuery.error, 'Не удалось загрузить занятия')} />
  }

  return (
    <div className="page-grid">
      <PageTitle
        title="Мои занятия"
        subtitle="Собственные занятия преподавателя, статический и динамический QR, переход к корректировкам"
        actions={
          <div className="row">
            <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </div>
        }
      />

      {error ? <ErrorBlock message={error} /> : null}

      {selectedQrLesson && staticQr ? (
        <Card>
          <div className="split-grid teacher-qr-grid">
            <div className="stack">
              <div className="space-between">
                <h3>Статический QR</h3>
                <Tag variant={qrStatusVariant(staticQr.expires_at)}>
                  {dayjs(staticQr.expires_at).isBefore(dayjs()) ? 'Истек' : `До ${formatDateTime(staticQr.expires_at)}`}
                </Tag>
              </div>
              <div className="muted-small">
                {selectedQrLesson.group_code} • {selectedQrLesson.group_name}
              </div>
              <div className="muted-small">
                {selectedQrLesson.discipline_name} • {formatDateTime(selectedQrLesson.starts_at)}
              </div>
              <div className="code teacher-code-block">{staticQr.deeplink}</div>
              <div className="row">
                <Button
                  variant="primary"
                  onClick={() => {
                    void navigator.clipboard.writeText(staticQr.deeplink)
                    toast.push('Deeplink скопирован', 'success')
                  }}
                >
                  Копировать deeplink
                </Button>
                <Button
                  onClick={() => {
                    setStaticQr(null)
                    setSelectedQrLesson(null)
                  }}
                >
                  Скрыть
                </Button>
              </div>
            </div>

            <div className="teacher-qr-box">
              <QRCode size={220} value={staticQr.deeplink} />
            </div>
          </div>
        </Card>
      ) : null}

      <Card>
        <Table
          rows={lessonsQuery.data ?? []}
          getRowKey={(row) => row.id}
          columns={[
            {
              key: 'time',
              title: 'Время',
              render: (row: TeacherLessonItem) => (
                <div className="stack">
                  <span>{formatDateTime(row.starts_at)}</span>
                  <span className="muted-small">до {formatDateTime(row.ends_at)}</span>
                </div>
              ),
            },
            {
              key: 'group',
              title: 'Группа',
              render: (row: TeacherLessonItem) => (
                <div className="stack">
                  <span>{row.group_name}</span>
                  <span className="muted-small">{row.group_code}</span>
                </div>
              ),
            },
            {
              key: 'discipline',
              title: 'Дисциплина',
              render: (row: TeacherLessonItem) => (
                <div className="stack">
                  <span>{row.discipline_name}</span>
                  <span className="muted-small">{row.discipline_code}</span>
                </div>
              ),
            },
            {
              key: 'status',
              title: 'Статус',
              render: (row: TeacherLessonItem) => (
                <Tag variant={lessonStatusVariant(row.status)}>{humanizeStatus(row.status)}</Tag>
              ),
            },
            {
              key: 'room',
              title: 'Аудитория',
              render: (row: TeacherLessonItem) => row.room || '-',
            },
            {
              key: 'actions',
              title: 'Действия',
              render: (row: TeacherLessonItem) => (
                <div className="row">
                  <Button
                    variant="primary"
                    disabled={staticQrMutation.isPending}
                    onClick={() => {
                      setError(null)
                      staticQrMutation.mutate(row.id)
                    }}
                  >
                    Показать QR
                  </Button>
                  <Button
                    disabled={dynamicMutation.isPending}
                    onClick={() => {
                      setError(null)
                      dynamicMutation.mutate(row.id)
                    }}
                  >
                    Динамический QR
                  </Button>
                  <Link className="link-btn" to={`/teacher/lessons/${row.id}/attendance`}>
                    Отметки
                  </Link>
                </div>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
