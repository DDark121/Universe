import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { adminApi } from '@/shared/api/adminApi'
import type { RiskListItem } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

export function RiskPage() {
  const toast = useToast()

  const [facultyId, setFacultyId] = useState('')
  const [streamId, setStreamId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [disciplineId, setDisciplineId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const facultiesQuery = useQuery({ queryKey: ['risk-faculties'], queryFn: () => adminApi.listFaculties() })
  const streamsQuery = useQuery({
    queryKey: ['risk-streams', facultyId],
    queryFn: () => adminApi.listStreams(facultyId || undefined),
  })
  const groupsQuery = useQuery({ queryKey: ['risk-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({ queryKey: ['risk-disciplines'], queryFn: () => adminApi.listDisciplines() })

  const riskQuery = useQuery({
    queryKey: ['risk-students', facultyId, streamId, groupId, disciplineId, dateFrom, dateTo],
    queryFn: () =>
      adminApi.listRiskStudents({
        ...(facultyId ? { faculty_id: facultyId } : {}),
        ...(streamId ? { stream_id: streamId } : {}),
        ...(groupId ? { group_id: groupId } : {}),
        ...(disciplineId ? { discipline_id: disciplineId } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }),
  })

  const warnMutation = useMutation({
    mutationFn: (studentId: string) => adminApi.warnRiskStudent(studentId),
    onSuccess: () => toast.push('Предупреждение отправлено', 'success'),
  })

  if (
    facultiesQuery.isLoading ||
    streamsQuery.isLoading ||
    groupsQuery.isLoading ||
    disciplinesQuery.isLoading ||
    riskQuery.isLoading
  ) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle title="Студенты в зоне риска" subtitle="Фильтрация по структуре, периоду и дисциплине" />

      <Card>
        <div className="form-grid">
          <Select value={facultyId} onChange={(e) => setFacultyId(e.target.value)}>
            <option value="">Факультет</option>
            {facultiesQuery.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select value={streamId} onChange={(e) => setStreamId(e.target.value)}>
            <option value="">Поток</option>
            {streamsQuery.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
          <Select value={groupId} onChange={(e) => setGroupId(e.target.value)}>
            <option value="">Группа</option>
            {groupsQuery.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
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
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
      </Card>

      {warnMutation.isError ? (
        <ErrorBlock message={getApiErrorMessage(warnMutation.error, 'Не удалось отправить предупреждение')} />
      ) : null}

      <Card>
        <Table
          rows={riskQuery.data ?? []}
          getRowKey={(row: RiskListItem) => row.student_id}
          columns={[
            {
              key: 'student_name',
              title: 'Студент',
              render: (row: RiskListItem) => <Link to={`/risk/${row.student_id}`}>{row.student_name}</Link>,
            },
            {
              key: 'score',
              title: 'Рейтинг',
              render: (row: RiskListItem) => <Tag variant={row.score < 60 ? 'danger' : 'warning'}>{row.score.toFixed(2)}</Tag>,
            },
            { key: 'lates', title: 'Опоздания', render: (row: RiskListItem) => row.late_count },
            {
              key: 'absences',
              title: 'Неуважительные пропуски',
              render: (row: RiskListItem) => row.unexcused_absence_count,
            },
            {
              key: 'reasons',
              title: 'Причины',
              render: (row: RiskListItem) => (
                <span className="muted-small">{Object.keys(row.reasons || {}).join(', ') || '-'}</span>
              ),
            },
            {
              key: 'actions',
              title: 'Действия',
              render: (row: RiskListItem) => (
                <div className="row">
                  <Button variant="primary" onClick={() => warnMutation.mutate(row.student_id)}>
                    Отправить предупреждение
                  </Button>
                  <Link className="link-btn" to={`/risk/${row.student_id}`}>
                    Открыть карточку
                  </Link>
                </div>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
