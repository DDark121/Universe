import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { Link } from 'react-router-dom'

import { adminApi } from '@/shared/api/adminApi'
import type { StudentAnalyticsItem } from '@/shared/api/types'
import { Card } from '@/shared/ui/Card'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { StatBar } from '@/shared/ui/StatBar'
import { StatCard } from '@/shared/ui/StatCard'

function studentStatusLabel(status: StudentAnalyticsItem['status']) {
  if (status === 'critical') return 'Критично'
  if (status === 'watch') return 'Наблюдать'
  if (status === 'stable') return 'Стабильно'
  return 'Нет отметок'
}

function StudentScoreRow({ item, tone }: { item: StudentAnalyticsItem; tone: 'best' | 'worst' }) {
  return (
    <Link className={`student-score-row student-score-row-${tone}`} to={`/risk/${item.student_id}`}>
      <span>
        <strong>{item.student_name}</strong>
        <small>
          {item.group_code} · {studentStatusLabel(item.status)}
        </small>
      </span>
      <span className="student-score-meter">
        <strong>{item.current_score.toFixed(1)}</strong>
        <small>
          {item.attendance_pct.toFixed(0)}% · late {item.late} · abs {item.unexcused_absent}
        </small>
      </span>
    </Link>
  )
}

export function DashboardPage() {
  const dateFrom = dayjs().startOf('month').format('YYYY-MM-DD')
  const dateTo = dayjs().format('YYYY-MM-DD')
  const usersQuery = useQuery({ queryKey: ['dashboard-users'], queryFn: () => adminApi.listUsers({ page_size: 200 }) })
  const groupsQuery = useQuery({ queryKey: ['dashboard-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({
    queryKey: ['dashboard-disciplines'],
    queryFn: () => adminApi.listDisciplines(),
  })
  const riskQuery = useQuery({ queryKey: ['dashboard-risk'], queryFn: () => adminApi.listRiskStudents() })
  const attendanceQuery = useQuery({
    queryKey: ['dashboard-attendance', dateFrom, dateTo],
    queryFn: () => adminApi.getAttendanceReport({ date_from: dateFrom, date_to: dateTo }),
  })
  const latesQuery = useQuery({
    queryKey: ['dashboard-lates', dateFrom, dateTo],
    queryFn: () => adminApi.getLatesReport({ date_from: dateFrom, date_to: dateTo, page_size: '100' }),
  })
  const studentAnalyticsQuery = useQuery({
    queryKey: ['dashboard-student-analytics', dateFrom, dateTo],
    queryFn: () => adminApi.getStudentAnalytics({ date_from: dateFrom, date_to: dateTo, limit: '5' }),
  })

  const loading =
    usersQuery.isLoading ||
    groupsQuery.isLoading ||
    disciplinesQuery.isLoading ||
    riskQuery.isLoading ||
    attendanceQuery.isLoading ||
    latesQuery.isLoading ||
    studentAnalyticsQuery.isLoading

  const roleDistribution = useMemo(() => {
    const users = usersQuery.data ?? []
    return {
      admin: users.filter((user) => user.roles.includes('admin')).length,
      curator: users.filter((user) => user.roles.includes('curator')).length,
      teacher: users.filter((user) => user.roles.includes('teacher')).length,
      student: users.filter((user) => user.roles.includes('student')).length,
    }
  }, [usersQuery.data])

  const riskSpotlight = useMemo(
    () =>
      [...(riskQuery.data ?? [])]
        .sort(
          (left, right) =>
            right.unexcused_absence_count + right.late_count - (left.unexcused_absence_count + left.late_count),
        )
        .slice(0, 3),
    [riskQuery.data],
  )

  const attendance = attendanceQuery.data
  const totalAttendanceEvents =
    (attendance?.present ?? 0) +
    (attendance?.late ?? 0) +
    (attendance?.absent ?? 0)
  const attendanceCoverage =
    totalAttendanceEvents === 0
      ? 0
      : Math.round((((attendance?.present ?? 0) + (attendance?.late ?? 0)) / totalAttendanceEvents) * 100)
  const studentAnalytics = studentAnalyticsQuery.data
  const scoredStudents = studentAnalytics?.items.filter((item) => item.status !== 'no_data') ?? []
  const averageStudentScore = scoredStudents.length
    ? Math.round(scoredStudents.reduce((sum, item) => sum + item.current_score, 0) / scoredStudents.length)
    : 0

  if (loading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle
        title="Панель управления"
        subtitle="Оперативный срез по данным дисциплины и посещаемости"
      />

      <Card>
        <div className="report-hero">
          <div className="report-hero-shell">
            <div className="report-hero-copy">
              <div className="panel-kicker">Campus Pulse</div>
              <h3>Единый взгляд на систему за текущий месяц</h3>
              <p className="muted">
                Attendance coverage {attendanceCoverage}% при {latesQuery.data?.length ?? 0} late-инцидентах.
                Ниже собраны оперативные сигналы по структуре пользователей и зоне риска.
              </p>
            </div>
            <div className="report-chip-grid">
              <div className="report-chip">
                <span>Период</span>
                <strong>{dateFrom} → {dateTo}</strong>
              </div>
              <div className="report-chip">
                <span>Событий</span>
                <strong>{totalAttendanceEvents}</strong>
              </div>
              <div className="report-chip">
                <span>Risk-сигналов</span>
                <strong>{riskQuery.data?.length ?? 0}</strong>
              </div>
              <div className="report-chip">
                <span>Студентов</span>
                <strong>{studentAnalytics?.total_students ?? 0}</strong>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <div className="stat-card-grid stagger-list">
        <StatCard label="Coverage" value={`${attendanceCoverage}%`} hint="Присутствие и late по всем событиям месяца." tone="ink" eyebrow="Core Metric" />
        <StatCard label="Пользователи" value={usersQuery.data?.length ?? 0} hint="Все активные роли в системе." tone="success" />
        <StatCard label="Группы" value={groupsQuery.data?.length ?? 0} hint="Учебные контуры, доступные в админке." tone="neutral" />
        <StatCard label="Дисциплины" value={disciplinesQuery.data?.length ?? 0} hint="Активные учебные предметы." tone="warning" />
        <StatCard label="Студенты в риске" value={riskQuery.data?.length ?? 0} hint="Текущая зона внимания по rating/risk." tone="danger" />
        <StatCard label="Student score" value={averageStudentScore || '-'} hint="Средний текущий score по студентам с отметками." tone="ink" />
      </div>

      <Card>
        <div className="student-intel-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">Student Pulse</div>
              <h3>Лучшие и худшие сейчас</h3>
            </div>
            <div className="student-intel-summary">
              <span>{studentAnalytics?.total_marks ?? 0} отметок</span>
              <strong>{studentAnalytics?.total_students ?? 0} студентов</strong>
            </div>
          </div>

          <div className="student-intel-grid">
            <section className="student-intel-lane">
              <div className="student-intel-lane-head">
                <span>В зоне внимания</span>
                <strong>{studentAnalytics?.worst[0]?.current_score.toFixed(1) ?? '-'}</strong>
              </div>
              <div className="student-score-list">
                {studentAnalytics?.worst.length ? (
                  studentAnalytics.worst.map((item) => <StudentScoreRow key={item.student_id} item={item} tone="worst" />)
                ) : (
                  <div className="dashboard-empty">Нет студентов с отметками за период.</div>
                )}
              </div>
            </section>

            <section className="student-intel-lane">
              <div className="student-intel-lane-head">
                <span>Сильнее всех</span>
                <strong>{studentAnalytics?.best[0]?.current_score.toFixed(1) ?? '-'}</strong>
              </div>
              <div className="student-score-list">
                {studentAnalytics?.best.length ? (
                  studentAnalytics.best.map((item) => <StudentScoreRow key={item.student_id} item={item} tone="best" />)
                ) : (
                  <div className="dashboard-empty">Пока нет устойчивых лидеров за период.</div>
                )}
              </div>
            </section>
          </div>
        </div>
      </Card>

      <div className="dashboard-matrix">
        <StatBar
          title="Распределение по ролям"
          totalLabel="Всего пользователей"
          totalValue={usersQuery.data?.length ?? 0}
          segments={[
            { label: 'Students', value: roleDistribution.student, tone: 'success' },
            { label: 'Teachers', value: roleDistribution.teacher, tone: 'warning' },
            { label: 'Curators', value: roleDistribution.curator, tone: 'neutral' },
            { label: 'Admins', value: roleDistribution.admin, tone: 'danger' },
          ]}
        />

        <Card>
          <div className="dashboard-spotlight">
            <div>
              <div className="panel-kicker">Risk Spotlight</div>
              <h3>Кого проверить первым</h3>
            </div>
            {riskSpotlight.length === 0 ? (
              <div className="dashboard-empty">Сейчас в active risk-списке никого нет.</div>
            ) : (
              riskSpotlight.map((item) => (
                <article key={item.student_id} className="dashboard-spotlight-card">
                  <strong>{item.student_name}</strong>
                  <p>
                    Score {item.score} · опоздания {item.late_count} · неуважительные пропуски{' '}
                    {item.unexcused_absence_count}
                  </p>
                </article>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card>
        <div className="panel-header">
          <div>
            <div className="panel-kicker">Quick Read</div>
            <h3>Операционные маркеры</h3>
          </div>
        </div>
        <div className="dashboard-mini-grid">
          <div className="dashboard-mini-card">
            <span>Present</span>
            <strong>{attendance?.present ?? 0}</strong>
          </div>
          <div className="dashboard-mini-card">
            <span>Late</span>
            <strong>{attendance?.late ?? 0}</strong>
          </div>
          <div className="dashboard-mini-card">
            <span>Absent</span>
            <strong>{attendance?.absent ?? 0}</strong>
          </div>
          <div className="dashboard-mini-card">
            <span>Unexcused</span>
            <strong>{attendance?.unexcused_absent ?? 0}</strong>
          </div>
        </div>
      </Card>
    </div>
  )
}
