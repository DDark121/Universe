import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'

import { adminApi } from '@/shared/api/adminApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { ActionChip } from '@/shared/ui/ActionChip'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { StatBar } from '@/shared/ui/StatBar'
import { StatCard } from '@/shared/ui/StatCard'
import { useToast } from '@/shared/ui/ToastProvider'

export function AttendanceReportPage() {
  const toast = useToast()

  const [dateFrom, setDateFrom] = useState(dayjs().startOf('month').format('YYYY-MM-DD'))
  const [dateTo, setDateTo] = useState(dayjs().format('YYYY-MM-DD'))
  const [studentId, setStudentId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [disciplineId, setDisciplineId] = useState('')
  const [teacherId, setTeacherId] = useState('')
  const [exportFormat, setExportFormat] = useState<'csv' | 'xlsx'>('xlsx')

  const usersQuery = useQuery({ queryKey: ['report-users'], queryFn: () => adminApi.listUsers() })
  const groupsQuery = useQuery({ queryKey: ['report-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({ queryKey: ['report-disciplines'], queryFn: () => adminApi.listDisciplines() })

  const reportQuery = useQuery({
    queryKey: ['attendance-report', dateFrom, dateTo, studentId, groupId, disciplineId, teacherId],
    queryFn: () =>
      adminApi.getAttendanceReport({
        date_from: dateFrom,
        date_to: dateTo,
        ...(studentId ? { student_id: studentId } : {}),
        ...(groupId ? { group_id: groupId } : {}),
        ...(disciplineId ? { discipline_id: disciplineId } : {}),
        ...(teacherId ? { teacher_id: teacherId } : {}),
      }),
    enabled: Boolean(dateFrom && dateTo),
  })

  const exportMutation = useMutation({
    mutationFn: () =>
      adminApi.createExport({
        job_type: 'report',
        format: exportFormat,
        filters: {
          report: 'attendance',
          date_from: dateFrom,
          date_to: dateTo,
          student_id: studentId || null,
          group_id: groupId || null,
          discipline_id: disciplineId || null,
          teacher_id: teacherId || null,
        },
      }),
    onSuccess: () => toast.push('Экспорт запущен. Статус в разделе Экспорт.', 'success'),
  })

  const teachers = useMemo(
    () => (usersQuery.data ?? []).filter((user) => user.roles.includes('teacher')),
    [usersQuery.data],
  )

  const selectedStudent = useMemo(
    () => usersQuery.data?.find((user) => user.id === studentId)?.full_name ?? 'Все студенты',
    [studentId, usersQuery.data],
  )
  const selectedTeacher = useMemo(
    () => teachers.find((teacher) => teacher.id === teacherId)?.full_name ?? 'Все преподаватели',
    [teacherId, teachers],
  )
  const selectedGroup = useMemo(
    () => groupsQuery.data?.find((group) => group.id === groupId)?.name ?? 'Все группы',
    [groupId, groupsQuery.data],
  )
  const selectedDiscipline = useMemo(
    () => disciplinesQuery.data?.find((item) => item.id === disciplineId)?.name ?? 'Все дисциплины',
    [disciplineId, disciplinesQuery.data],
  )

  const summary = reportQuery.data
  const totalEvents =
    (summary?.present ?? 0) +
    (summary?.late ?? 0) +
    (summary?.absent ?? 0)
  const attendanceCoverage = totalEvents === 0 ? 0 : Math.round((((summary?.present ?? 0) + (summary?.late ?? 0)) / totalEvents) * 100)
  const punctualityRate =
    (summary?.present ?? 0) + (summary?.late ?? 0) === 0
      ? 0
      : Math.round(((summary?.present ?? 0) / ((summary?.present ?? 0) + (summary?.late ?? 0))) * 100)
  const activeFilters = [studentId, teacherId, groupId, disciplineId].filter(Boolean).length

  if (usersQuery.isLoading || groupsQuery.isLoading || disciplinesQuery.isLoading || reportQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle title="Отчет посещаемости" subtitle="Сводный отчет по посещаемости за выбранный период" />

      <Card>
        <div className="control-stack">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">Filters</div>
              <h3>Срез отчета</h3>
              <p className="muted">Соберите период и нужный контур: студент, преподаватель, группа или дисциплина.</p>
            </div>
          </div>
          <div className="form-grid">
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            <Select value={studentId} onChange={(e) => setStudentId(e.target.value)}>
              <option value="">Студент</option>
              {usersQuery.data?.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name}
                </option>
              ))}
            </Select>
            <Select value={teacherId} onChange={(e) => setTeacherId(e.target.value)}>
              <option value="">Преподаватель</option>
              {teachers.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>
                  {teacher.full_name}
                </option>
              ))}
            </Select>
            <Select value={groupId} onChange={(e) => setGroupId(e.target.value)}>
              <option value="">Группа</option>
              {groupsQuery.data?.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </Select>
            <Select value={disciplineId} onChange={(e) => setDisciplineId(e.target.value)}>
              <option value="">Дисциплина</option>
              {disciplinesQuery.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      <Card>
        <div className="report-hero">
          <div className="report-hero-shell">
            <div className="report-hero-copy">
              <div className="panel-kicker">Attendance Pulse</div>
              <h3>Картина посещаемости за выбранный период</h3>
              <p className="muted">
                Покрытие посещаемости {attendanceCoverage}% при пунктуальности {punctualityRate}%. Чем выше доля
                late и unexcused absence, тем быстрее этот срез перейдёт в risk-сигналы.
              </p>
            </div>
            <div className="report-chip-grid">
              <div className="report-chip">
                <span>Период</span>
                <strong>{dateFrom} → {dateTo}</strong>
              </div>
              <div className="report-chip">
                <span>Активных фильтров</span>
                <strong>{activeFilters || 'Базовый срез'}</strong>
              </div>
              <div className="report-chip">
                <span>Событий</span>
                <strong>{totalEvents}</strong>
              </div>
            </div>
          </div>
          <div className="summary-grid">
            <div className="summary-tile">
              <span className="summary-label">Студент</span>
              <span className="summary-value">{selectedStudent}</span>
            </div>
            <div className="summary-tile">
              <span className="summary-label">Преподаватель</span>
              <span className="summary-value">{selectedTeacher}</span>
            </div>
            <div className="summary-tile">
              <span className="summary-label">Группа</span>
              <span className="summary-value">{selectedGroup}</span>
            </div>
            <div className="summary-tile">
              <span className="summary-label">Дисциплина</span>
              <span className="summary-value">{selectedDiscipline}</span>
            </div>
          </div>
        </div>
      </Card>

      <div className="stat-card-grid stagger-list">
        <StatCard
          label="Покрытие посещаемости"
          value={`${attendanceCoverage}%`}
          hint="Present + late от общего числа событий."
          tone="ink"
          eyebrow="Core Metric"
        />
        <StatCard
          label="Присутствовали"
          value={summary?.present ?? 0}
          hint="Вошли в окно и отметились без опоздания."
          tone="success"
        />
        <StatCard
          label="Опоздали"
          value={summary?.late ?? 0}
          hint="Нужен отдельный контроль по времени входа."
          tone="warning"
        />
        <StatCard
          label="Пропустили"
          value={summary?.absent ?? 0}
          hint="Все пропуски независимо от причины."
          tone="danger"
        />
        <StatCard
          label="Неуважительные"
          value={summary?.unexcused_absent ?? 0}
          hint="Это ядро для risk и эскалаций."
          tone="neutral"
        />
      </div>

      <div className="split-grid">
        <StatBar
          title="Структура событий"
          totalLabel="Всего записей"
          totalValue={totalEvents}
          segments={[
            { label: 'Present', value: summary?.present ?? 0, tone: 'success' },
            { label: 'Late', value: summary?.late ?? 0, tone: 'warning' },
            { label: 'Absent', value: summary?.absent ?? 0, tone: 'danger' },
            { label: 'Excused', value: summary?.excused_absent ?? 0, tone: 'neutral' },
          ]}
        />

        <Card>
          <div className="control-stack">
            <div className="panel-header">
              <div>
                <div className="panel-kicker">Attendance Export</div>
                <h3>Выгрузка отчета</h3>
                <p className="muted">Собранный фильтрами срез можно сразу отправить в очередь экспорта.</p>
              </div>
            </div>

            <div className="summary-grid">
              <div className="summary-tile">
                <span className="summary-label">Период</span>
                <span className="summary-value">
                  {dateFrom} → {dateTo}
                </span>
              </div>
              <div className="summary-tile">
                <span className="summary-label">Формат</span>
                <span className="summary-value">{exportFormat.toUpperCase()}</span>
              </div>
              <div className="summary-tile">
                <span className="summary-label">Пунктуальность</span>
                <span className="summary-value">{punctualityRate}%</span>
              </div>
            </div>

            <div className="toolbar-line">
              <Select value={exportFormat} onChange={(e) => setExportFormat(e.target.value as 'csv' | 'xlsx')}>
                <option value="xlsx">XLSX</option>
                <option value="csv">CSV</option>
              </Select>
              <div className="toolbar-actions">
                <ActionChip variant="primary" onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>
                  Запустить экспорт
                </ActionChip>
              </div>
            </div>
          </div>
          {exportMutation.isError ? (
            <ErrorBlock message={getApiErrorMessage(exportMutation.error, 'Не удалось запустить экспорт')} />
          ) : null}
        </Card>
      </div>
    </div>
  )
}
