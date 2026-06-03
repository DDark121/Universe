import { useEffect, useEffectEvent, useRef, useState } from 'react'
import QRCode from 'react-qr-code'
import dayjs from 'dayjs'
import { Link, useParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'

import { teacherApi, buildTeacherWsUrl } from '@/shared/api/teacherApi'
import type { TeacherQrSessionClosedEvent, TeacherQrSlotEvent } from '@/shared/api/types'
import { useAuth } from '@/shared/auth/AuthContext'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDateTime } from '@/shared/utils/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

type ConnectionState = 'connecting' | 'connected' | 'closed' | 'error'

function connectionVariant(state: ConnectionState) {
  if (state === 'connected') return 'success' as const
  if (state === 'error') return 'danger' as const
  if (state === 'closed') return 'warning' as const
  return 'default' as const
}

export function TeacherQrSessionPage() {
  const { session } = useAuth()
  const { sessionId } = useParams<{ sessionId: string }>()
  const toast = useToast()
  const socketRef = useRef<WebSocket | null>(null)
  const accessToken = session?.accessToken ?? null
  const hasSessionContext = Boolean(sessionId && accessToken)
  const missingSessionError = 'Отсутствует session ID или access token'

  const [connectionState, setConnectionState] = useState<ConnectionState>(hasSessionContext ? 'connecting' : 'error')
  const [error, setError] = useState<string | null>(null)
  const [deeplink, setDeeplink] = useState<string | null>(null)
  const [slotIndex, setSlotIndex] = useState<number | null>(null)
  const [expiresAt, setExpiresAt] = useState<string | null>(null)
  const [lessonId, setLessonId] = useState<string | null>(null)

  const resetConnectionState = useEffectEvent(() => {
    setConnectionState('connecting')
    setError(null)
  })

  useEffect(() => {
    if (!hasSessionContext) return

    resetConnectionState()
    const socket = new WebSocket(buildTeacherWsUrl(`/api/v1/teacher/qr/sessions/${sessionId}/stream`, accessToken!))
    socketRef.current = socket

    socket.onopen = () => {
      setConnectionState('connected')
    }

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as
        | TeacherQrSlotEvent
        | TeacherQrSessionClosedEvent
        | { error?: string }

      if ('error' in payload && payload.error) {
        setConnectionState('error')
        setError(payload.error)
        return
      }

      if ('event' in payload && payload.event === 'session_closed') {
        setConnectionState('closed')
        setError('Сессия закрыта сервером')
        socket.close()
        return
      }

      if ('event' in payload && payload.event === 'qr_slot') {
        setConnectionState('connected')
        setDeeplink(payload.deeplink)
        setSlotIndex(payload.slot_index)
        setExpiresAt(payload.expires_at)
        setLessonId(payload.lesson_id)
      }
    }

    socket.onerror = () => {
      setConnectionState('error')
      setError('Ошибка WebSocket-соединения')
    }

    socket.onclose = () => {
      setConnectionState((currentState) => (currentState === 'error' ? currentState : 'closed'))
    }

    return () => {
      socket.close()
      socketRef.current = null
    }
  }, [accessToken, hasSessionContext, sessionId])

  const stopMutation = useMutation({
    mutationFn: () => teacherApi.stopDynamicQrSession(sessionId ?? ''),
    onSuccess: () => {
      socketRef.current?.close()
      setConnectionState('closed')
      toast.push('QR-сессия остановлена', 'success')
    },
    onError: (mutationError) => {
      setError(getApiErrorMessage(mutationError, 'Не удалось остановить QR-сессию'))
    },
  })

  if (!sessionId) {
    return <ErrorBlock message="Некорректный session ID" />
  }

  const effectiveConnectionState = hasSessionContext ? connectionState : 'error'
  const effectiveError = hasSessionContext ? error : missingSessionError

  return (
    <div className="page-grid">
      <PageTitle
        title="Динамический QR"
        subtitle="Токен обновляется автоматически через WebSocket"
        actions={
          <div className="row">
            <Tag variant={connectionVariant(effectiveConnectionState)}>{effectiveConnectionState}</Tag>
            <Link className="link-btn" to="/teacher/lessons">
              Вернуться к занятиям
            </Link>
          </div>
        }
      />

      {effectiveError ? <ErrorBlock message={effectiveError} /> : null}

      <div className="split-grid teacher-qr-grid">
        <Card>
          <div className="stack">
            <h3>Состояние сессии</h3>
            <div className="row space-between">
              <span className="muted-small">Session ID</span>
              <span className="code">{sessionId}</span>
            </div>
            <div className="row space-between">
              <span className="muted-small">Lesson ID</span>
              <span className="code">{lessonId ?? '-'}</span>
            </div>
            <div className="row space-between">
              <span className="muted-small">Текущий слот</span>
              <span className="mono">{slotIndex ?? '-'}</span>
            </div>
            <div className="row space-between">
              <span className="muted-small">Истекает</span>
              <span>{formatDateTime(expiresAt)}</span>
            </div>
            <div className="code teacher-code-block">{deeplink ?? 'Ожидаем первый qr_slot...'}</div>
            <div className="row">
              <Button
                variant="primary"
                disabled={!deeplink}
                onClick={() => {
                  if (!deeplink) return
                  void navigator.clipboard.writeText(deeplink)
                  toast.push('Deeplink скопирован', 'success')
                }}
              >
                Копировать deeplink
              </Button>
              <Button
                variant="danger"
                disabled={stopMutation.isPending || connectionState === 'closed'}
                onClick={() => stopMutation.mutate()}
              >
                {stopMutation.isPending ? 'Остановка...' : 'Остановить сессию'}
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <div className="teacher-qr-box teacher-qr-box-large">
            {deeplink ? (
              <QRCode size={280} value={deeplink} />
            ) : (
              <div className="muted">
                {connectionState === 'connecting'
                  ? 'Подключаемся к WebSocket...'
                  : dayjs(expiresAt).isBefore(dayjs())
                    ? 'Сессия завершена'
                    : 'Ожидаем данные QR'}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
