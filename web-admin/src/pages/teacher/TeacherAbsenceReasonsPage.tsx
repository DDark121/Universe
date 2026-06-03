import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { teacherApi } from '@/shared/api/teacherApi'
import type { TeacherAbsenceReasonItem } from '@/shared/api/types'
import { downloadBlob } from '@/shared/utils/file'
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

function statusVariant(status: TeacherAbsenceReasonItem['status']) {
  if (status === 'accepted') return 'success' as const
  if (status === 'rejected') return 'danger' as const
  return 'warning' as const
}

export function TeacherAbsenceReasonsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [statusFilter, setStatusFilter] = useState<'all' | TeacherAbsenceReasonItem['status']>('all')
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [downloadingAttachmentId, setDownloadingAttachmentId] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['teacher-absence-reasons'],
    queryFn: () => teacherApi.listAbsenceReasons(),
  })

  const moderateMutation = useMutation({
    mutationFn: (payload: { reason_id: string; status: 'accepted' | 'rejected'; comment?: string }) =>
      teacherApi.moderateAbsenceReason(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['teacher-absence-reasons'] })
      toast.push('Решение по причине сохранено', 'success')
    },
    onError: (mutationError) => {
      setError(getApiErrorMessage(mutationError, 'Не удалось сохранить решение'))
    },
  })

  const filteredRows = useMemo(() => {
    const rows = query.data ?? []
    if (statusFilter === 'all') return rows
    return rows.filter((row) => row.status === statusFilter)
  }, [query.data, statusFilter])

  if (query.isLoading) {
    return <Loader />
  }

  if (query.isError) {
    return <ErrorBlock message={getApiErrorMessage(query.error, 'Не удалось загрузить причины отсутствия')} />
  }

  return (
    <div className="page-grid">
      <PageTitle
        title="Причины отсутствия"
        subtitle="Модерация причин по собственным занятиям и загрузка приложенных файлов"
        actions={
          <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
            <option value="all">Все статусы</option>
            <option value="pending">На модерации</option>
            <option value="accepted">Приняты</option>
            <option value="rejected">Отклонены</option>
          </Select>
        }
      />

      {error ? <ErrorBlock message={error} /> : null}

      <Card>
        <Table
          rows={filteredRows}
          getRowKey={(row) => row.id}
          columns={[
            {
              key: 'student',
              title: 'Студент / занятие',
              render: (row: TeacherAbsenceReasonItem) => (
                <div className="stack">
                  <span>{row.student_name}</span>
                  <span className="muted-small">{row.group_name}</span>
                  <span className="muted-small">{formatDateTime(row.lesson_starts_at)}</span>
                </div>
              ),
            },
            {
              key: 'reason',
              title: 'Причина',
              render: (row: TeacherAbsenceReasonItem) => (
                <div className="stack">
                  <div className="row">
                    <Tag>{humanizeStatus(row.reason_type)}</Tag>
                    {row.is_predeclared ? <Tag variant="warning">Заявлено заранее</Tag> : null}
                  </div>
                  <span>{row.comment || '-'}</span>
                </div>
              ),
            },
            {
              key: 'attachments',
              title: 'Вложения',
              render: (row: TeacherAbsenceReasonItem) => (
                <div className="stack">
                  {row.attachments.length === 0 ? <span className="muted-small">Нет файлов</span> : null}
                  {row.attachments.map((attachment) => (
                    <button
                      key={attachment.id}
                      className="link-btn"
                      disabled={downloadingAttachmentId === attachment.id}
                      onClick={async () => {
                        try {
                          setDownloadingAttachmentId(attachment.id)
                          const blob = await teacherApi.downloadAbsenceAttachment(attachment.id)
                          downloadBlob(blob, attachment.file_name)
                        } catch (downloadError) {
                          setError(getApiErrorMessage(downloadError, 'Не удалось скачать файл'))
                        } finally {
                          setDownloadingAttachmentId(null)
                        }
                      }}
                    >
                      {attachment.file_name} ({Math.ceil(attachment.size_bytes / 1024)} KB)
                    </button>
                  ))}
                </div>
              ),
            },
            {
              key: 'status',
              title: 'Текущий статус',
              render: (row: TeacherAbsenceReasonItem) => (
                <div className="stack">
                  <Tag variant={statusVariant(row.status)}>{humanizeStatus(row.status)}</Tag>
                  <span className="muted-small">{row.moderation_comment || 'Без комментария'}</span>
                </div>
              ),
            },
            {
              key: 'comment',
              title: 'Комментарий преподавателя',
              render: (row: TeacherAbsenceReasonItem) => (
                <Input
                  value={commentDrafts[row.id] ?? ''}
                  placeholder="Необязательный комментарий"
                  onChange={(event) => {
                    setCommentDrafts((previous) => ({
                      ...previous,
                      [row.id]: event.target.value,
                    }))
                  }}
                />
              ),
            },
            {
              key: 'actions',
              title: 'Действия',
              render: (row: TeacherAbsenceReasonItem) => (
                <div className="row">
                  <Button
                    variant="primary"
                    disabled={moderateMutation.isPending}
                    onClick={() => {
                      setError(null)
                      moderateMutation.mutate({
                        reason_id: row.id,
                        status: 'accepted',
                        comment: commentDrafts[row.id] || undefined,
                      })
                    }}
                  >
                    Принять
                  </Button>
                  <Button
                    variant="danger"
                    disabled={moderateMutation.isPending}
                    onClick={() => {
                      setError(null)
                      moderateMutation.mutate({
                        reason_id: row.id,
                        status: 'rejected',
                        comment: commentDrafts[row.id] || undefined,
                      })
                    }}
                  >
                    Отклонить
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
