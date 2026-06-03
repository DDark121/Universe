import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import { teacherApi } from '@/shared/api/teacherApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Textarea } from '@/shared/ui/Textarea'
import { useToast } from '@/shared/ui/ToastProvider'

export function TeacherBroadcastsPage() {
  const toast = useToast()
  const [groupId, setGroupId] = useState('')
  const [message, setMessage] = useState('')

  const groupsQuery = useQuery({
    queryKey: ['teacher-groups-for-broadcast'],
    queryFn: () => teacherApi.listGroups(),
  })

  const sendMutation = useMutation({
    mutationFn: () => teacherApi.createBroadcast({ group_id: groupId, message }),
    onSuccess: () => {
      setMessage('')
      toast.push('Сообщение поставлено в очередь', 'success')
    },
  })

  if (groupsQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle
        title="Рассылки преподавателя"
        subtitle="Отправка Telegram-сообщений собственным группам"
      />

      {groupsQuery.isError ? (
        <ErrorBlock message={getApiErrorMessage(groupsQuery.error, 'Не удалось загрузить группы')} />
      ) : null}

      <Card>
        <div className="form-grid">
          <Select value={groupId} onChange={(event) => setGroupId(event.target.value)}>
            <option value="">Выберите группу</option>
            {groupsQuery.data?.map((group) => (
              <option key={group.id} value={group.id}>
                {group.code} • {group.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="stack" style={{ marginTop: 10 }}>
          <span className="muted-small">Сообщение</span>
          <Textarea
            value={message}
            rows={6}
            maxLength={2000}
            placeholder="Введите текст сообщения для студентов"
            onChange={(event) => setMessage(event.target.value)}
          />
          <div className="row-end">
            <Button
              variant="primary"
              disabled={!groupId || !message.trim() || sendMutation.isPending}
              onClick={() => sendMutation.mutate()}
            >
              {sendMutation.isPending ? 'Отправка...' : 'Отправить'}
            </Button>
          </div>
        </div>
        {sendMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(sendMutation.error, 'Не удалось отправить рассылку')} />
        ) : null}
      </Card>
    </div>
  )
}
