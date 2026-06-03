import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'

import { adminApi } from '@/shared/api/adminApi'
import { formatDateTime } from '@/shared/utils/format'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { StatBar } from '@/shared/ui/StatBar'
import { StatCard } from '@/shared/ui/StatCard'

export function LatesReportPage() {
  const [dateFrom, setDateFrom] = useState(dayjs().startOf('month').format('YYYY-MM-DD'))
  const [dateTo, setDateTo] = useState(dayjs().format('YYYY-MM-DD'))
  const [studentId, setStudentId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [disciplineId, setDisciplineId] = useState('')
  const [teacherId, setTeacherId] = useState('')

  const usersQuery = useQuery({ queryKey: ['lates-users'], queryFn: () => adminApi.listUsers() })
  const groupsQuery = useQuery({ queryKey: ['lates-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({ queryKey: ['lates-disciplines'], queryFn: () => adminApi.listDisciplines() })

  const query = useQuery({
    queryKey: ['lates-report', dateFrom, dateTo, studentId, groupId, disciplineId, teacherId],
    queryFn: () =>
      adminApi.getLatesReport({
        date_from: dateFrom,
        date_to: dateTo,
        ...(studentId ? { student_id: studentId } : {}),
        ...(groupId ? { group_id: groupId } : {}),
        ...(disciplineId ? { discipline_id: disciplineId } : {}),
        ...(teacherId ? { teacher_id: teacherId } : {}),
      }),
  })

  const teachers = useMemo(
    () => (usersQuery.data ?? []).filter((user) => user.roles.includes('teacher')),
    [usersQuery.data],
  )
  const rows = query.data ?? []
  const uniqueStudents = new Set(rows.map((row) => row.student_id)).size
  const uniqueGroups = new Set(rows.map((row) => row.group_id)).size
  const uniqueDisciplines = new Set(rows.map((row) => row.discipline_id)).size
  const lateDurations = rows.map((row) => Math.max(dayjs(row.marked_at).diff(dayjs(row.starts_at), 'minute'), 1))
  const averageDelay = lateDurations.length === 0 ? 0 : Math.round(lateDurations.reduce((sum, value) => sum + value, 0) / lateDurations.length)
  const maxDelay = lateDurations.length === 0 ? 0 : Math.max(...lateDurations)
  const severity = lateDurations.reduce(
    (acc, value) => {
      if (value >= 20) {
        acc.critical += 1
      } else if (value >= 10) {
        acc.elevated += 1
      } else {
        acc.light += 1
      }
      return acc
    },
    { light: 0, elevated: 0, critical: 0 },
  )

  if (query.isLoading || usersQuery.isLoading || groupsQuery.isLoading || disciplinesQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle title="Отчет по опозданиям" subtitle="Детализация опозданий по занятиям" />

      <Card>
        <div className="control-stack">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">Late Filters</div>
              <h3>Контур анализа</h3>
              <p className="muted">Оставьте общий поток или заузьте срез до конкретного студента, группы или преподавателя.</p>
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
              <div className="panel-kicker">Late Signals</div>
              <h3>Лента опозданий без табличного шума</h3>
              <p className="muted">
                Средняя задержка {averageDelay} мин. Максимум {maxDelay} мин. Это помогает быстро отделить
                лёгкие дисциплинарные шумы от системных сбоев расписания.
              </p>
            </div>
            <div className="report-chip-grid">
              <div className="report-chip">
                <span>Период</span>
                <strong>{dateFrom} → {dateTo}</strong>
              </div>
              <div className="report-chip">
                <span>Инцидентов</span>
                <strong>{rows.length}</strong>
              </div>
              <div className="report-chip">
                <span>Затронуто студентов</span>
                <strong>{uniqueStudents}</strong>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <div className="stat-card-grid stagger-list">
        <StatCard label="Всего late-отметок" value={rows.length} hint="Все события после стартового дедлайна." tone="ink" eyebrow="Late Feed" />
        <StatCard label="Студенты" value={uniqueStudents} hint="Сколько разных студентов попали в late." tone="warning" />
        <StatCard label="Группы" value={uniqueGroups} hint="Число групп, где есть инциденты." tone="neutral" />
        <StatCard label="Дисциплины" value={uniqueDisciplines} hint="Сколько предметов дали late-сигналы." tone="success" />
        <StatCard label="Пиковая задержка" value={`${maxDelay} мин`} hint="Максимальное фактическое отклонение." tone="danger" />
      </div>

      <StatBar
        title="Распределение по тяжести"
        totalLabel="Всего late"
        totalValue={rows.length}
        segments={[
          { label: 'До 10 мин', value: severity.light, tone: 'neutral' },
          { label: '10–19 мин', value: severity.elevated, tone: 'warning' },
          { label: '20+ мин', value: severity.critical, tone: 'danger' },
        ]}
      />

      <Card>
        <div className="control-stack">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">Late Feed</div>
              <h3>Детализация по инцидентам</h3>
              <p className="muted">Карточный поток удобнее для ручного разбора, чем широкая таблица со смещающимися колонками.</p>
            </div>
          </div>
          {rows.length === 0 ? (
            <div className="dashboard-empty">За выбранный период опозданий нет.</div>
          ) : (
            <div className="late-feed">
              {rows.map((row) => {
                const delayMinutes = Math.max(dayjs(row.marked_at).diff(dayjs(row.starts_at), 'minute'), 1)
                const groupName = groupsQuery.data?.find((group) => group.id === row.group_id)?.name ?? row.group_id
                const disciplineName =
                  disciplinesQuery.data?.find((item) => item.id === row.discipline_id)?.name ?? row.discipline_id
                const teacherName = teachers.find((teacher) => teacher.id === row.teacher_id)?.full_name ?? row.teacher_id

                return (
                  <article key={row.attendance_id} className="late-card">
                    <div className="late-card-head">
                      <div className="late-card-title">
                        <strong>{row.student_name}</strong>
                        <span>{disciplineName}</span>
                      </div>
                      <span className="late-badge">+{delayMinutes} мин</span>
                    </div>
                    <div className="late-card-meta">
                      <span>Занятие: {formatDateTime(row.starts_at)}</span>
                      <span>Отметка: {formatDateTime(row.marked_at)}</span>
                    </div>
                    <div className="summary-grid">
                      <div className="summary-tile">
                        <span className="summary-label">Группа</span>
                        <span className="summary-value">{groupName}</span>
                      </div>
                      <div className="summary-tile">
                        <span className="summary-label">Преподаватель</span>
                        <span className="summary-value">{teacherName}</span>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
