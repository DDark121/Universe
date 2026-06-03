import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { adminApi } from '@/shared/api/adminApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDate, formatDateTime } from '@/shared/utils/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

export function RiskStudentPage() {
  const { studentId } = useParams<{ studentId: string }>()
  const toast = useToast()

  const query = useQuery({
    queryKey: ['risk-student', studentId],
    queryFn: () => adminApi.getRiskStudent(studentId ?? ''),
    enabled: Boolean(studentId),
  })

  const warnMutation = useMutation({
    mutationFn: () => adminApi.warnRiskStudent(studentId ?? ''),
    onSuccess: () => toast.push('Предупреждение отправлено', 'success'),
  })

  if (!studentId) {
    return <ErrorBlock message="Некорректный ID студента" />
  }

  if (query.isLoading) {
    return <Loader />
  }

  if (query.isError || !query.data) {
    return <ErrorBlock message={getApiErrorMessage(query.error, 'Не удалось загрузить карточку риска')} />
  }

  const detail = query.data

  return (
    <div className="page-grid">
      <PageTitle
        title={`Карточка риска: ${detail.student.full_name}`}
        subtitle={`@${detail.student.username}`}
        actions={
          <div className="row">
            <Button variant="primary" onClick={() => warnMutation.mutate()}>
              Отправить предупреждение
            </Button>
            <Link className="link-btn" to="/risk">
              Вернуться к списку
            </Link>
          </div>
        }
      />

      <div className="stats-grid stagger-list">
        <Card>
          <div className="muted-small">Текущий рейтинг</div>
          <div className="kpi-value">{detail.risk_card?.score?.toFixed(2) ?? '-'}</div>
        </Card>
        <Card>
          <div className="muted-small">Опозданий</div>
          <div className="kpi-value">{detail.risk_card?.late_count ?? 0}</div>
        </Card>
        <Card>
          <div className="muted-small">Неуважительных пропусков</div>
          <div className="kpi-value">{detail.risk_card?.unexcused_absence_count ?? 0}</div>
        </Card>
      </div>

      {warnMutation.isError ? (
        <ErrorBlock message={getApiErrorMessage(warnMutation.error, 'Не удалось отправить предупреждение')} />
      ) : null}

      <div className="split-grid">
        <Card>
          <h3>Динамика рейтинга</h3>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <LineChart data={detail.ratings.slice().reverse()}>
                <XAxis dataKey="period_end" tickFormatter={(v) => formatDate(v)} />
                <YAxis domain={[0, 100]} />
                <Tooltip
                  labelFormatter={(value) => formatDate(String(value))}
                />
                <Line type="monotone" dataKey="score" stroke="#4F6734" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <h3>Сработавшие причины риска</h3>
          <div className="stack">
            {Object.entries(detail.risk_card?.reasons ?? {}).map(([key, value]) => (
              <div key={key} className="row space-between">
                <span>{key}</span>
                <Tag>{String(value)}</Tag>
              </div>
            ))}
            {!Object.keys(detail.risk_card?.reasons ?? {}).length ? <span className="muted">Нет данных</span> : null}
          </div>
        </Card>
      </div>

      <Card>
        <h3>Прогноз риска (14/28 дней)</h3>
        <Table
          rows={detail.forecasts ?? []}
          getRowKey={(row) => `${row.horizon_days}-${row.calculated_for_date}`}
          columns={[
            { key: 'horizon', title: 'Горизонт', render: (row) => `${row.horizon_days} дн.` },
            { key: 'score', title: 'Прогноз score', render: (row) => row.predicted_score.toFixed(2) },
            { key: 'lates', title: 'Прогноз опозданий', render: (row) => row.predicted_late_count },
            {
              key: 'unexcused',
              title: 'Прогноз неуваж. пропусков',
              render: (row) => row.predicted_unexcused_absence_count,
            },
            { key: 'confidence', title: 'Уверенность', render: (row) => `${row.confidence}%` },
            { key: 'date', title: 'Дата расчета', render: (row) => formatDate(row.calculated_for_date) },
          ]}
        />
      </Card>

      <Card>
        <h3>История причин отсутствия</h3>
        <Table
          rows={detail.absence_reasons}
          getRowKey={(row) => row.reason_id}
          columns={[
            { key: 'lesson', title: 'Занятие', render: (row) => formatDateTime(row.lesson_starts_at) },
            { key: 'type', title: 'Тип', render: (row) => row.reason_type },
            { key: 'comment', title: 'Комментарий', render: (row) => row.comment || '-' },
            {
              key: 'status',
              title: 'Модерация',
              render: (row) => {
                const variant = row.moderation_status === 'accepted' ? 'success' : row.moderation_status === 'rejected' ? 'danger' : 'warning'
                return <Tag variant={variant}>{row.moderation_status}</Tag>
              },
            },
            { key: 'moderated_at', title: 'Дата решения', render: (row) => formatDateTime(row.moderated_at) },
          ]}
        />
      </Card>

      <Card>
        <h3>История эскалаций</h3>
        <Table
          rows={detail.escalations}
          getRowKey={(row) => row.id}
          columns={[
            { key: 'created', title: 'Создано', render: (row) => formatDateTime(row.created_at) },
            {
              key: 'status',
              title: 'Статус',
              render: (row) => <Tag variant={row.status === 'resolved' ? 'success' : 'warning'}>{row.status}</Tag>,
            },
            { key: 'reason', title: 'Причины', render: (row) => JSON.stringify(row.reason_payload) },
            { key: 'resolved_at', title: 'Закрыто', render: (row) => formatDateTime(row.resolved_at) },
          ]}
        />
      </Card>
    </div>
  )
}
