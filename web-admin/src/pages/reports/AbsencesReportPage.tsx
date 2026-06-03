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
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'

export function AbsencesReportPage() {
  const [dateFrom, setDateFrom] = useState(dayjs().startOf('month').format('YYYY-MM-DD'))
  const [dateTo, setDateTo] = useState(dayjs().format('YYYY-MM-DD'))
  const [studentId, setStudentId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [disciplineId, setDisciplineId] = useState('')
  const [teacherId, setTeacherId] = useState('')
  const [excused, setExcused] = useState<'all' | 'true' | 'false'>('all')

  const usersQuery = useQuery({ queryKey: ['abs-users'], queryFn: () => adminApi.listUsers() })
  const groupsQuery = useQuery({ queryKey: ['abs-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({ queryKey: ['abs-disciplines'], queryFn: () => adminApi.listDisciplines() })

  const query = useQuery({
    queryKey: ['absences-report', dateFrom, dateTo, studentId, groupId, disciplineId, teacherId, excused],
    queryFn: () =>
      adminApi.getAbsencesReport({
        date_from: dateFrom,
        date_to: dateTo,
        ...(studentId ? { student_id: studentId } : {}),
        ...(groupId ? { group_id: groupId } : {}),
        ...(disciplineId ? { discipline_id: disciplineId } : {}),
        ...(teacherId ? { teacher_id: teacherId } : {}),
        ...(excused !== 'all' ? { excused } : {}),
      }),
  })

  const teachers = useMemo(
    () => (usersQuery.data ?? []).filter((user) => user.roles.includes('teacher')),
    [usersQuery.data],
  )

  if (query.isLoading || usersQuery.isLoading || groupsQuery.isLoading || disciplinesQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle title="Отчет по пропускам" subtitle="Уважительные и неуважительные пропуски" />

      <Card>
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
          <Select value={excused} onChange={(e) => setExcused(e.target.value as 'all' | 'true' | 'false')}>
            <option value="all">Все</option>
            <option value="true">Только уважительные</option>
            <option value="false">Только неуважительные</option>
          </Select>
        </div>
      </Card>

      <Card>
        <Table
          rows={(query.data as Array<Record<string, string | boolean>>) ?? []}
          getRowKey={(row) => String(row.attendance_id)}
          columns={[
            { key: 'student_name', title: 'Студент', render: (row) => row.student_name },
            { key: 'starts_at', title: 'Занятие', render: (row) => formatDateTime(String(row.starts_at)) },
            {
              key: 'excused',
              title: 'Тип',
              render: (row) =>
                row.is_excused ? <Tag variant="success">Уважительный</Tag> : <Tag variant="danger">Неуважительный</Tag>,
            },
            { key: 'category', title: 'Категория', render: (row) => (row.excused_category as string) || '-' },
            {
              key: 'group',
              title: 'Группа',
              render: (row) =>
                groupsQuery.data?.find((group) => group.id === (row.group_id as string))?.name ?? String(row.group_id),
            },
            {
              key: 'discipline',
              title: 'Дисциплина',
              render: (row) =>
                disciplinesQuery.data?.find((item) => item.id === (row.discipline_id as string))?.name ??
                String(row.discipline_id),
            },
          ]}
        />
      </Card>
    </div>
  )
}
