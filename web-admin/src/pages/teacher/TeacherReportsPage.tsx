import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'

import { teacherApi } from '@/shared/api/teacherApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { StatBar } from '@/shared/ui/StatBar'
import { StatCard } from '@/shared/ui/StatCard'

export function TeacherReportsPage() {
  const [dateFrom, setDateFrom] = useState(dayjs().startOf('month').format('YYYY-MM-DD'))
  const [dateTo, setDateTo] = useState(dayjs().format('YYYY-MM-DD'))
  const [groupId, setGroupId] = useState('')
  const [submittedRange, setSubmittedRange] = useState({ dateFrom, dateTo, groupId: '' })

  const groupsQuery = useQuery({
    queryKey: ['teacher-report-groups'],
    queryFn: () => teacherApi.listGroups(),
  })

  const summaryQuery = useQuery({
    queryKey: ['teacher-attendance-summary', submittedRange.dateFrom, submittedRange.dateTo, submittedRange.groupId],
    queryFn: () =>
      teacherApi.getAttendanceReport({
        date_from: submittedRange.dateFrom,
        date_to: submittedRange.dateTo,
        ...(submittedRange.groupId ? { group_id: submittedRange.groupId } : {}),
      }),
  })

  if (groupsQuery.isLoading || summaryQuery.isLoading) {
    return <Loader />
  }

  if (groupsQuery.isError) {
    return <ErrorBlock message={getApiErrorMessage(groupsQuery.error, 'Не удалось загрузить список групп')} />
  }

  if (summaryQuery.isError) {
    return <ErrorBlock message={getApiErrorMessage(summaryQuery.error, 'Не удалось загрузить отчет')} />
  }

  const selectedGroupName =
    groupsQuery.data?.find((group) => group.id === submittedRange.groupId)?.name ?? 'Все мои группы'
  const summary = summaryQuery.data
  const totalEvents =
    (summary?.present ?? 0) +
    (summary?.late ?? 0) +
    (summary?.absent ?? 0)
  const attendanceCoverage = totalEvents === 0 ? 0 : Math.round((((summary?.present ?? 0) + (summary?.late ?? 0)) / totalEvents) * 100)
  const punctualityRate =
    (summary?.present ?? 0) + (summary?.late ?? 0) === 0
      ? 0
      : Math.round(((summary?.present ?? 0) / ((summary?.present ?? 0) + (summary?.late ?? 0))) * 100)

  return (
    <div className="page-grid">
      <PageTitle
        title="Отчет посещаемости"
        subtitle="Сводный teacher-отчет по периоду и группе. Подробные опоздания/пропуски остаются в следующей итерации."
      />

      <Card>
        <div className="control-stack">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">Teacher Scope</div>
              <h3>Фильтры отчета</h3>
              <p className="muted">Выберите период и группу, чтобы быстро проверить дисциплину посещаемости.</p>
            </div>
          </div>
          <div className="form-grid">
            <label>
              Дата с
              <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </label>
            <label>
              Дата по
              <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </label>
            <label>
              Группа
              <Select value={groupId} onChange={(event) => setGroupId(event.target.value)}>
                <option value="">Все мои группы</option>
                {groupsQuery.data?.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.code} • {group.name}
                  </option>
                ))}
              </Select>
            </label>
            <div className="row-end">
              <Button
                variant="primary"
                onClick={() => {
                  setSubmittedRange({ dateFrom, dateTo, groupId })
                }}
              >
                Обновить
              </Button>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div className="report-hero">
          <div className="report-hero-shell">
            <div className="report-hero-copy">
              <div className="panel-kicker">Teacher Pulse</div>
              <h3>Как группа проходит через ваши занятия</h3>
              <p className="muted">
                Attendance coverage {attendanceCoverage}% и punctuality {punctualityRate}% по выбранному набору занятий.
                Это быстрый сигнал, когда нужно вмешиваться вручную или усиливать QR-дисциплину.
              </p>
            </div>
            <div className="report-chip-grid">
              <div className="report-chip">
                <span>Период</span>
                <strong>{submittedRange.dateFrom} → {submittedRange.dateTo}</strong>
              </div>
              <div className="report-chip">
                <span>Группа</span>
                <strong>{selectedGroupName}</strong>
              </div>
              <div className="report-chip">
                <span>Событий</span>
                <strong>{totalEvents}</strong>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <div className="stat-card-grid stagger-list">
        <StatCard label="Coverage" value={`${attendanceCoverage}%`} hint="Присутствие вместе с late." tone="ink" eyebrow="Core Metric" />
        <StatCard label="Присутствовали" value={summary?.present ?? 0} hint="Отмечены без опоздания." tone="success" />
        <StatCard label="Опоздали" value={summary?.late ?? 0} hint="Вход после дедлайна пары." tone="warning" />
        <StatCard label="Пропустили" value={summary?.absent ?? 0} hint="Все отсутствия по периоду." tone="danger" />
        <StatCard label="Неуважительные" value={summary?.unexcused_absent ?? 0} hint="Главный источник риска и эскалаций." tone="neutral" />
      </div>

      <StatBar
        title="Структура teacher-отчета"
        totalLabel="Всего событий"
        totalValue={totalEvents}
        segments={[
          { label: 'Present', value: summary?.present ?? 0, tone: 'success' },
          { label: 'Late', value: summary?.late ?? 0, tone: 'warning' },
          { label: 'Absent', value: summary?.absent ?? 0, tone: 'danger' },
          { label: 'Excused', value: summary?.excused_absent ?? 0, tone: 'neutral' },
        ]}
      />
    </div>
  )
}
