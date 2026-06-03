import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Textarea } from '@/shared/ui/Textarea'
import { useToast } from '@/shared/ui/ToastProvider'

export function TutorPushesPage() {
  const toast = useToast()
  const [groupId, setGroupId] = useState('')
  const [message, setMessage] = useState('')

  const groupsQuery = useQuery({
    queryKey: ['tutor-groups'],
    queryFn: () => adminApi.listTutorGroups(),
  })

  const sendMutation = useMutation({
    mutationFn: () => adminApi.createTutorBroadcast({ group_id: groupId, message }),
    onSuccess: () => {
      setMessage('')
      toast.push('Пуш отправлен в очередь', 'success')
    },
  })

  return (
    <div className="page-grid">
      <PageTitle
        title="Рассылки тьютора"
        subtitle="Отправка сообщений в Telegram по доступным группам"
      />

      <Card>
        <div className="form-grid">
          <Select value={groupId} onChange={(e) => setGroupId(e.target.value)}>
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
            placeholder="Введите текст сообщения для группы"
            onChange={(e) => setMessage(e.target.value)}
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
