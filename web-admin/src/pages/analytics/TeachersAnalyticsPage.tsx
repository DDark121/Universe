import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { adminApi } from '@/shared/api/adminApi'
import type { TeacherAnalyticsItem } from '@/shared/api/types'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'

export function TeachersAnalyticsPage() {
  const [dateFrom, setDateFrom] = useState(dayjs().startOf('month').format('YYYY-MM-DD'))
  const [dateTo, setDateTo] = useState(dayjs().format('YYYY-MM-DD'))
  const [selectedTeachers, setSelectedTeachers] = useState<string[]>([])

  const usersQuery = useQuery({ queryKey: ['analytics-users'], queryFn: () => adminApi.listUsers({ role: 'teacher' }) })
  const analyticsQuery = useQuery({
    queryKey: ['teacher-analytics', dateFrom, dateTo],
    queryFn: () => adminApi.getTeacherAnalytics({ date_from: dateFrom, date_to: dateTo }),
  })

  const compareQuery = useQuery({
    queryKey: ['teacher-analytics-compare', dateFrom, dateTo, selectedTeachers],
    queryFn: () =>
      adminApi.compareTeacherAnalytics({
        date_from: dateFrom,
        date_to: dateTo,
        ...(selectedTeachers.length ? { teacher_ids: selectedTeachers } : {}),
      }),
  })

  const teacherMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const user of usersQuery.data ?? []) {
      map.set(user.id, user.full_name)
    }
    return map
  }, [usersQuery.data])

  if (usersQuery.isLoading || analyticsQuery.isLoading || compareQuery.isLoading) {
    return <Loader />
  }

  const chartRows = (compareQuery.data ?? []).map((row) => ({
    teacher: teacherMap.get(row.teacher_id) ?? row.teacher_id,
    attendance: row.attendance_pct,
    lates: row.lates ?? 0,
    absences: row.absences ?? 0,
  }))

  return (
    <div className="page-grid">
      <PageTitle title="Аналитика преподавателей" subtitle="Средняя посещаемость и сравнительный режим" />

      <Card>
        <div className="form-grid">
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          <Select
            multiple
            value={selectedTeachers}
            onChange={(e) => {
              const values = Array.from(e.target.selectedOptions).map((option) => option.value)
              setSelectedTeachers(values)
            }}
            style={{ minHeight: 120 }}
          >
            {usersQuery.data?.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <Card>
        <h3>Сравнение преподавателей</h3>
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={chartRows}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,22,30,0.15)" />
              <XAxis dataKey="teacher" tick={{ fontSize: 12 }} interval={0} angle={-18} textAnchor="end" height={70} />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip />
              <Legend />
              <Bar yAxisId="left" dataKey="attendance" name="Посещаемость %" fill="#4F6734" />
              <Bar yAxisId="right" dataKey="lates" name="Опоздания" fill="#51625C" />
              <Bar yAxisId="right" dataKey="absences" name="Пропуски" fill="#0B161E" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <Table
          rows={analyticsQuery.data ?? []}
          getRowKey={(row: TeacherAnalyticsItem) => row.teacher_id}
          columns={[
            {
              key: 'teacher',
              title: 'Преподаватель',
              render: (row: TeacherAnalyticsItem) => teacherMap.get(row.teacher_id) ?? row.teacher_id,
            },
            {
              key: 'attendance_pct',
              title: 'Посещаемость, %',
              render: (row: TeacherAnalyticsItem) => row.attendance_pct.toFixed(2),
            },
            {
              key: 'total_marks',
              title: 'Всего отметок',
              render: (row: TeacherAnalyticsItem) => row.total_marks,
            },
          ]}
        />
      </Card>
    </div>
  )
}
