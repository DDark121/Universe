import { startTransition, useEffect, useEffectEvent, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import type {
  AIImportDraftDetail,
  AIImportFacultyRow,
  AIImportGroupRow,
  AIImportPayload,
  AIImportStreamRow,
  AIImportUserRow,
  RoleCode,
} from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { formatDateTime } from '@/shared/utils/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { Textarea } from '@/shared/ui/Textarea'
import { useToast } from '@/shared/ui/ToastProvider'

type PreviewTab = 'summary' | 'structure' | 'users' | 'schedule' | 'issues'

const ROLE_OPTIONS: RoleCode[] = ['student', 'teacher', 'admin', 'curator']

function statusVariant(status: string) {
  if (status === 'draft' || status === 'applied') return 'success' as const
  if (status === 'failed' || status === 'rejected') return 'danger' as const
  return 'warning' as const
}

function parseRoles(raw: string): RoleCode[] {
  const tokens = raw
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter((item): item is RoleCode => ROLE_OPTIONS.includes(item as RoleCode))
  return Array.from(new Set(tokens))
}

function clonePayload(payload: AIImportPayload): AIImportPayload {
  return structuredClone(payload)
}

export function AiImportDraftPage() {
  const { draftId } = useParams<{ draftId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()

  const [tab, setTab] = useState<PreviewTab>('summary')
  const [payload, setPayload] = useState<AIImportPayload | null>(null)
  const [wizard, setWizard] = useState<AIImportDraftDetail['wizard']>({
    term_start: null,
    term_end: null,
    first_week_parity: null,
  })
  const [localError, setLocalError] = useState<string | null>(null)

  const draftQuery = useQuery({
    queryKey: ['ai-import-draft', draftId],
    queryFn: () => adminApi.getAIImport(draftId ?? ''),
    enabled: Boolean(draftId),
  })
  const facultiesQuery = useQuery({ queryKey: ['ai-import-faculties'], queryFn: () => adminApi.listFaculties() })
  const streamsQuery = useQuery({ queryKey: ['ai-import-streams'], queryFn: () => adminApi.listStreams() })
  const groupsQuery = useQuery({ queryKey: ['ai-import-groups'], queryFn: () => adminApi.listGroups() })
  const disciplinesQuery = useQuery({ queryKey: ['ai-import-disciplines'], queryFn: () => adminApi.listDisciplines() })
  const usersQuery = useQuery({ queryKey: ['ai-import-users'], queryFn: () => adminApi.listUsers() })

  const syncDraftState = useEffectEvent((draft: AIImportDraftDetail) => {
    startTransition(() => {
      setWizard(draft.wizard ?? { term_start: null, term_end: null, first_week_parity: null })
      setPayload(draft.payload ? clonePayload(draft.payload) : null)
    })
  })

  useEffect(() => {
    if (!draftQuery.data) return
    syncDraftState(draftQuery.data)
  }, [draftQuery.data])

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!draftId || !payload) throw new Error('Draft is not ready')
      return adminApi.updateAIImport(draftId, { wizard, payload })
    },
    onSuccess: (nextDraft) => {
      setPayload(nextDraft.payload ? clonePayload(nextDraft.payload) : null)
      setWizard(nextDraft.wizard)
      setLocalError(null)
      void queryClient.invalidateQueries({ queryKey: ['ai-import-drafts'] })
      void queryClient.invalidateQueries({ queryKey: ['ai-import-draft', draftId] })
      toast.push('AI draft сохранен', 'success')
    },
    onError: (error) => setLocalError(getApiErrorMessage(error, 'Не удалось сохранить draft')),
  })

  const applyMutation = useMutation({
    mutationFn: async () => {
      if (!draftId) throw new Error('Draft not found')
      return adminApi.applyAIImport(draftId)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['ai-import-drafts'] })
      await queryClient.invalidateQueries({ queryKey: ['ai-import-draft', draftId] })
      toast.push('AI import применен', 'success')
    },
    onError: (error) => setLocalError(getApiErrorMessage(error, 'Не удалось применить AI import')),
  })

  const rejectMutation = useMutation({
    mutationFn: async () => {
      if (!draftId) throw new Error('Draft not found')
      return adminApi.rejectAIImport(draftId)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['ai-import-drafts'] })
      toast.push('AI import отклонен', 'success')
      navigate('/imports')
    },
    onError: (error) => setLocalError(getApiErrorMessage(error, 'Не удалось отклонить draft')),
  })

  const issueCount = useMemo(
    () => draftQuery.data?.issues.filter((issue) => issue.requires_action || issue.severity === 'error').length ?? 0,
    [draftQuery.data],
  )

  function mutatePayload(mutator: (next: AIImportPayload) => void) {
    setPayload((prev) => {
      if (!prev) return prev
      const next = clonePayload(prev)
      mutator(next)
      return next
    })
  }

  function updateFacultyRow(draftKey: string, patch: Partial<AIImportFacultyRow>) {
    mutatePayload((next) => {
      next.entities.faculties = next.entities.faculties.map((row) => (row.draft_id === draftKey ? { ...row, ...patch } : row))
    })
  }

  function updateStreamRow(draftKey: string, patch: Partial<AIImportStreamRow>) {
    mutatePayload((next) => {
      next.entities.streams = next.entities.streams.map((row) => (row.draft_id === draftKey ? { ...row, ...patch } : row))
    })
  }

  function updateGroupRow(draftKey: string, patch: Partial<AIImportGroupRow>) {
    mutatePayload((next) => {
      next.entities.groups = next.entities.groups.map((row) => (row.draft_id === draftKey ? { ...row, ...patch } : row))
    })
  }

  function updateDisciplineRow(draftKey: string, patch: Partial<AIImportPayload['entities']['disciplines'][number]>) {
    mutatePayload((next) => {
      next.entities.disciplines = next.entities.disciplines.map((row) =>
        row.draft_id === draftKey ? { ...row, ...patch } : row,
      )
    })
  }

  function updateUserRow(draftKey: string, patch: Partial<AIImportUserRow>) {
    mutatePayload((next) => {
      next.entities.users = next.entities.users.map((row) => (row.draft_id === draftKey ? { ...row, ...patch } : row))
    })
  }

  function removeEntityRow(
    section: keyof AIImportPayload['entities'],
    draftKey: string,
  ) {
    mutatePayload((next) => {
      next.entities[section] = next.entities[section].filter((row) => row.draft_id !== draftKey) as never
    })
  }

  function updatePatternRow(
    draftKey: string,
    patch: Partial<AIImportPayload['schedule_patterns'][number]>,
  ) {
    mutatePayload((next) => {
      next.schedule_patterns = next.schedule_patterns.map((row) => (row.draft_id === draftKey ? { ...row, ...patch } : row))
    })
  }

  function removePatternRow(draftKey: string) {
    mutatePayload((next) => {
      next.schedule_patterns = next.schedule_patterns.filter((row) => row.draft_id !== draftKey)
      next.lessons = next.lessons.filter((row) => row.pattern_draft_id !== draftKey)
    })
  }

  if (draftQuery.isLoading || facultiesQuery.isLoading || streamsQuery.isLoading || groupsQuery.isLoading || disciplinesQuery.isLoading || usersQuery.isLoading) {
    return <Loader />
  }

  if (!draftQuery.data) {
    return <ErrorBlock message="AI import draft не найден" />
  }

  const draft = draftQuery.data
  const canEdit = draft.status === 'draft' && payload

  return (
    <div className="page-grid">
      <PageTitle
        title="AI Import Preview"
        subtitle="Редактирование нормализованного draft перед применением в систему"
        actions={
          <div className="row">
            <Link className="link-btn" to="/imports">
              Назад к импортам
            </Link>
            <Tag variant={statusVariant(draft.status)}>{draft.status}</Tag>
          </div>
        }
      />

      {localError ? <ErrorBlock message={localError} /> : null}

      <Card>
        <div className="space-between">
          <div className="stack">
            <strong>{draft.file_name}</strong>
            <span className="muted-small">
              Создан: {formatDateTime(draft.created_at)} • Обновлен: {formatDateTime(draft.updated_at || draft.created_at)}
            </span>
          </div>
          <div className="row">
            <Button onClick={() => void draftQuery.refetch()}>Обновить</Button>
            <Button variant="primary" disabled={!canEdit || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
              {saveMutation.isPending ? 'Сохраняем...' : 'Сохранить draft'}
            </Button>
            <Button
              variant="primary"
              disabled={draft.status !== 'draft' || applyMutation.isPending}
              onClick={() => applyMutation.mutate()}
            >
              {applyMutation.isPending ? 'Применяем...' : 'Применить'}
            </Button>
            <Button variant="danger" disabled={rejectMutation.isPending} onClick={() => rejectMutation.mutate()}>
              {rejectMutation.isPending ? 'Отклоняем...' : 'Отклонить'}
            </Button>
          </div>
        </div>
      </Card>

      {!payload ? (
        <Card>
          <p className="muted">Draft еще не готов к редактированию. Дождитесь завершения обработки или откройте error report.</p>
          {draft.error_report ? <pre>{JSON.stringify(draft.error_report, null, 2)}</pre> : null}
        </Card>
      ) : (
        <>
          <Card>
            <div className="row">
              {(['summary', 'structure', 'users', 'schedule', 'issues'] as PreviewTab[]).map((item) => (
                <Button
                  key={item}
                  variant={tab === item ? 'primary' : 'secondary'}
                  onClick={() => setTab(item)}
                >
                  {item === 'summary'
                    ? 'Сводка'
                    : item === 'structure'
                      ? 'Структура'
                      : item === 'users'
                        ? 'Пользователи'
                        : item === 'schedule'
                          ? 'Расписание'
                          : `Проблемы (${issueCount})`}
                </Button>
              ))}
            </div>
          </Card>

          {tab === 'summary' ? (
            <div className="page-grid">
              <Card>
                <div className="detail-grid">
                  <div>
                    <div className="muted-small">Режим</div>
                    <div className="kpi-value" style={{ fontSize: '1.15rem' }}>{draft.mode}</div>
                  </div>
                  <div>
                    <div className="muted-small">Тип документа</div>
                    <div className="kpi-value" style={{ fontSize: '1.15rem' }}>{draft.summary?.detected_doc_kind ?? '-'}</div>
                  </div>
                  <div>
                    <div className="muted-small">Confidence</div>
                    <div className="kpi-value" style={{ fontSize: '1.15rem' }}>{draft.summary?.confidence ?? 0}</div>
                  </div>
                  <div>
                    <div className="muted-small">Проблемы</div>
                    <div className="kpi-value" style={{ fontSize: '1.15rem' }}>{draft.summary?.counts?.issues ?? 0}</div>
                  </div>
                </div>
              </Card>

              <Card>
                <h3>Календарь импорта</h3>
                <div className="form-grid">
                  <Input
                    type="date"
                    value={wizard.term_start ?? ''}
                    onChange={(event) => setWizard((prev) => ({ ...prev, term_start: event.target.value || null }))}
                    disabled={draft.mode === 'users'}
                  />
                  <Input
                    type="date"
                    value={wizard.term_end ?? ''}
                    onChange={(event) => setWizard((prev) => ({ ...prev, term_end: event.target.value || null }))}
                    disabled={draft.mode === 'users'}
                  />
                  <Select
                    value={wizard.first_week_parity ?? ''}
                    onChange={(event) =>
                      setWizard((prev) => ({
                        ...prev,
                        first_week_parity: (event.target.value as 'odd' | 'even') || null,
                      }))
                    }
                    disabled={draft.mode === 'users'}
                  >
                    <option value="">Базовая чет/нечет</option>
                    <option value="odd">Первая неделя нечетная</option>
                    <option value="even">Первая неделя четная</option>
                  </Select>
                </div>
              </Card>

              <Card>
                <h3>Source Excerpt</h3>
                <Textarea value={draft.summary?.excerpt ?? ''} readOnly />
              </Card>

              <Card>
                <h3>Заметки AI</h3>
                {payload.notes.length ? (
                  <div className="stack">
                    {payload.notes.map((note, index) => (
                      <div key={`${note}-${index}`} className="muted-small">
                        {note}
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="muted">Нет заметок</span>
                )}
              </Card>
            </div>
          ) : null}

          {tab === 'structure' ? (
            <div className="page-grid">
              <Card>
                <h3>Факультеты</h3>
                <Table
                  rows={payload.entities.faculties}
                  getRowKey={(row) => row.draft_id}
                  columns={[
                    {
                      key: 'code',
                      title: 'Code',
                      render: (row) => (
                        <Input value={row.code ?? ''} onChange={(event) => updateFacultyRow(row.draft_id, { code: event.target.value })} />
                      ),
                    },
                    {
                      key: 'name',
                      title: 'Name',
                      render: (row) => (
                        <Input value={row.name ?? ''} onChange={(event) => updateFacultyRow(row.draft_id, { name: event.target.value })} />
                      ),
                    },
                    {
                      key: 'mapping',
                      title: 'Mapping',
                      render: (row) => (
                        <div className="stack">
                          <Select
                            value={row.action}
                            onChange={(event) =>
                              updateFacultyRow(row.draft_id, {
                                action: event.target.value as AIImportFacultyRow['action'],
                                existing_id: event.target.value === 'match_existing' ? row.existing_id ?? null : null,
                              })
                            }
                          >
                            <option value="unresolved">unresolved</option>
                            <option value="match_existing">match_existing</option>
                            <option value="create_new">create_new</option>
                          </Select>
                          {row.action === 'match_existing' ? (
                            <Select
                              value={row.existing_id ?? ''}
                              onChange={(event) => updateFacultyRow(row.draft_id, { existing_id: event.target.value || null })}
                            >
                              <option value="">Выберите факультет</option>
                              {facultiesQuery.data?.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.code} • {item.name}
                                </option>
                              ))}
                            </Select>
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: 'actions',
                      title: 'Действия',
                      render: (row) => <Button onClick={() => removeEntityRow('faculties', row.draft_id)}>Удалить</Button>,
                    },
                  ]}
                />
              </Card>

              <Card>
                <h3>Потоки</h3>
                <Table
                  rows={payload.entities.streams}
                  getRowKey={(row) => row.draft_id}
                  columns={[
                    {
                      key: 'name',
                      title: 'Name',
                      render: (row) => (
                        <Input value={row.name ?? ''} onChange={(event) => updateStreamRow(row.draft_id, { name: event.target.value })} />
                      ),
                    },
                    {
                      key: 'faculty_code',
                      title: 'Faculty Code',
                      render: (row) => (
                        <Input
                          value={row.faculty_code ?? ''}
                          onChange={(event) => updateStreamRow(row.draft_id, { faculty_code: event.target.value })}
                        />
                      ),
                    },
                    {
                      key: 'mapping',
                      title: 'Mapping',
                      render: (row) => (
                        <div className="stack">
                          <Select
                            value={row.action}
                            onChange={(event) =>
                              updateStreamRow(row.draft_id, {
                                action: event.target.value as AIImportStreamRow['action'],
                                existing_id: event.target.value === 'match_existing' ? row.existing_id ?? null : null,
                              })
                            }
                          >
                            <option value="unresolved">unresolved</option>
                            <option value="match_existing">match_existing</option>
                            <option value="create_new">create_new</option>
                          </Select>
                          {row.action === 'match_existing' ? (
                            <Select
                              value={row.existing_id ?? ''}
                              onChange={(event) => updateStreamRow(row.draft_id, { existing_id: event.target.value || null })}
                            >
                              <option value="">Выберите поток</option>
                              {streamsQuery.data?.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.name}
                                </option>
                              ))}
                            </Select>
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: 'actions',
                      title: 'Действия',
                      render: (row) => <Button onClick={() => removeEntityRow('streams', row.draft_id)}>Удалить</Button>,
                    },
                  ]}
                />
              </Card>

              <Card>
                <h3>Группы</h3>
                <Table
                  rows={payload.entities.groups}
                  getRowKey={(row) => row.draft_id}
                  columns={[
                    {
                      key: 'code',
                      title: 'Code',
                      render: (row) => (
                        <Input value={row.code ?? ''} onChange={(event) => updateGroupRow(row.draft_id, { code: event.target.value })} />
                      ),
                    },
                    {
                      key: 'name',
                      title: 'Name',
                      render: (row) => (
                        <Input value={row.name ?? ''} onChange={(event) => updateGroupRow(row.draft_id, { name: event.target.value })} />
                      ),
                    },
                    {
                      key: 'faculty_code',
                      title: 'Faculty',
                      render: (row) => (
                        <Input
                          value={row.faculty_code ?? ''}
                          onChange={(event) => updateGroupRow(row.draft_id, { faculty_code: event.target.value })}
                        />
                      ),
                    },
                    {
                      key: 'mapping',
                      title: 'Mapping',
                      render: (row) => (
                        <div className="stack">
                          <Select
                            value={row.action}
                            onChange={(event) =>
                              updateGroupRow(row.draft_id, {
                                action: event.target.value as AIImportGroupRow['action'],
                                existing_id: event.target.value === 'match_existing' ? row.existing_id ?? null : null,
                              })
                            }
                          >
                            <option value="unresolved">unresolved</option>
                            <option value="match_existing">match_existing</option>
                            <option value="create_new">create_new</option>
                          </Select>
                          {row.action === 'match_existing' ? (
                            <Select
                              value={row.existing_id ?? ''}
                              onChange={(event) => updateGroupRow(row.draft_id, { existing_id: event.target.value || null })}
                            >
                              <option value="">Выберите группу</option>
                              {groupsQuery.data?.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.code} • {item.name}
                                </option>
                              ))}
                            </Select>
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: 'actions',
                      title: 'Действия',
                      render: (row) => <Button onClick={() => removeEntityRow('groups', row.draft_id)}>Удалить</Button>,
                    },
                  ]}
                />
              </Card>

              <Card>
                <h3>Дисциплины</h3>
                <Table
                  rows={payload.entities.disciplines}
                  getRowKey={(row) => row.draft_id}
                  columns={[
                    {
                      key: 'code',
                      title: 'Code',
                      render: (row) => (
                        <Input
                          value={row.code ?? ''}
                          onChange={(event) => updateDisciplineRow(row.draft_id, { code: event.target.value })}
                        />
                      ),
                    },
                    {
                      key: 'name',
                      title: 'Name',
                      render: (row) => (
                        <Input
                          value={row.name ?? ''}
                          onChange={(event) => updateDisciplineRow(row.draft_id, { name: event.target.value })}
                        />
                      ),
                    },
                    {
                      key: 'mapping',
                      title: 'Mapping',
                      render: (row) => (
                        <div className="stack">
                          <Select
                            value={row.action}
                            onChange={(event) =>
                              updateDisciplineRow(row.draft_id, {
                                action: event.target.value as AIImportPayload['entities']['disciplines'][number]['action'],
                                existing_id: event.target.value === 'match_existing' ? row.existing_id ?? null : null,
                              })
                            }
                          >
                            <option value="unresolved">unresolved</option>
                            <option value="match_existing">match_existing</option>
                            <option value="create_new">create_new</option>
                          </Select>
                          {row.action === 'match_existing' ? (
                            <Select
                              value={row.existing_id ?? ''}
                              onChange={(event) => updateDisciplineRow(row.draft_id, { existing_id: event.target.value || null })}
                            >
                              <option value="">Выберите дисциплину</option>
                              {disciplinesQuery.data?.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.code} • {item.name}
                                </option>
                              ))}
                            </Select>
                          ) : null}
                        </div>
                      ),
                    },
                    {
                      key: 'actions',
                      title: 'Действия',
                      render: (row) => <Button onClick={() => removeEntityRow('disciplines', row.draft_id)}>Удалить</Button>,
                    },
                  ]}
                />
              </Card>
            </div>
          ) : null}

          {tab === 'users' ? (
            <Card>
              <h3>Пользователи</h3>
              <Table
                rows={payload.entities.users}
                getRowKey={(row) => row.draft_id}
                columns={[
                  {
                    key: 'username',
                    title: 'Username',
                    render: (row) => (
                      <Input value={row.username ?? ''} onChange={(event) => updateUserRow(row.draft_id, { username: event.target.value })} />
                    ),
                  },
                  {
                    key: 'full_name',
                    title: 'ФИО',
                    render: (row) => (
                      <Input value={row.full_name ?? ''} onChange={(event) => updateUserRow(row.draft_id, { full_name: event.target.value })} />
                    ),
                  },
                  {
                    key: 'email',
                    title: 'Email',
                    render: (row) => (
                      <Input value={row.email ?? ''} onChange={(event) => updateUserRow(row.draft_id, { email: event.target.value || null })} />
                    ),
                  },
                  {
                    key: 'roles',
                    title: 'Роли',
                    render: (row) => (
                      <Input
                        value={row.roles.join(', ')}
                        onChange={(event) => updateUserRow(row.draft_id, { roles: parseRoles(event.target.value) })}
                      />
                    ),
                  },
                  {
                    key: 'mapping',
                    title: 'Mapping',
                    render: (row) => (
                      <div className="stack">
                        <Select
                          value={row.action}
                          onChange={(event) =>
                            updateUserRow(row.draft_id, {
                              action: event.target.value as AIImportUserRow['action'],
                              existing_id: event.target.value === 'match_existing' ? row.existing_id ?? null : null,
                            })
                          }
                        >
                          <option value="unresolved">unresolved</option>
                          <option value="match_existing">match_existing</option>
                          <option value="create_new">create_new</option>
                        </Select>
                        {row.action === 'match_existing' ? (
                          <Select
                            value={row.existing_id ?? ''}
                            onChange={(event) => updateUserRow(row.draft_id, { existing_id: event.target.value || null })}
                          >
                            <option value="">Выберите пользователя</option>
                            {usersQuery.data?.map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.username} • {item.full_name}
                              </option>
                            ))}
                          </Select>
                        ) : null}
                      </div>
                    ),
                  },
                  {
                    key: 'actions',
                    title: 'Действия',
                    render: (row) => <Button onClick={() => removeEntityRow('users', row.draft_id)}>Удалить</Button>,
                  },
                ]}
              />
            </Card>
          ) : null}

          {tab === 'schedule' ? (
            <div className="page-grid">
              <Card>
                <h3>Шаблоны расписания</h3>
                <Table
                  rows={payload.schedule_patterns}
                  getRowKey={(row) => row.draft_id}
                  columns={[
                    {
                      key: 'group_code',
                      title: 'Group',
                      render: (row) => (
                        <Input
                          value={row.group_code ?? ''}
                          onChange={(event) => updatePatternRow(row.draft_id, { group_code: event.target.value })}
                        />
                      ),
                    },
                    {
                      key: 'discipline',
                      title: 'Discipline',
                      render: (row) => (
                        <div className="stack">
                          <Input
                            value={row.discipline_code ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { discipline_code: event.target.value })}
                            placeholder="Code"
                          />
                          <Input
                            value={row.discipline_name ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { discipline_name: event.target.value })}
                            placeholder="Name"
                          />
                        </div>
                      ),
                    },
                    {
                      key: 'teacher',
                      title: 'Teacher',
                      render: (row) => (
                        <div className="stack">
                          <Input
                            value={row.teacher_username ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { teacher_username: event.target.value })}
                            placeholder="Username"
                          />
                          <Input
                            value={row.teacher_name ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { teacher_name: event.target.value })}
                            placeholder="Full name"
                          />
                        </div>
                      ),
                    },
                    {
                      key: 'time',
                      title: 'Время',
                      render: (row) => (
                        <div className="stack">
                          <Input
                            type="date"
                            value={row.date ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { date: event.target.value || null })}
                          />
                          <Input
                            value={row.day_of_week ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { day_of_week: event.target.value || null })}
                            placeholder="monday"
                          />
                          <Input
                            value={row.start_time ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { start_time: event.target.value })}
                            placeholder="08:30"
                          />
                          <Input
                            value={row.end_time ?? ''}
                            onChange={(event) => updatePatternRow(row.draft_id, { end_time: event.target.value })}
                            placeholder="10:00"
                          />
                        </div>
                      ),
                    },
                    {
                      key: 'room',
                      title: 'Room / parity',
                      render: (row) => (
                        <div className="stack">
                          <Input value={row.room ?? ''} onChange={(event) => updatePatternRow(row.draft_id, { room: event.target.value })} />
                          <Select
                            value={row.week_parity}
                            onChange={(event) =>
                              updatePatternRow(row.draft_id, { week_parity: event.target.value as 'all' | 'odd' | 'even' })
                            }
                          >
                            <option value="all">all</option>
                            <option value="odd">odd</option>
                            <option value="even">even</option>
                          </Select>
                        </div>
                      ),
                    },
                    {
                      key: 'actions',
                      title: 'Действия',
                      render: (row) => <Button onClick={() => removePatternRow(row.draft_id)}>Удалить</Button>,
                    },
                  ]}
                />
              </Card>

              <Card>
                <h3>Развернутые занятия</h3>
                <Table
                  rows={payload.lessons.slice(0, 100)}
                  getRowKey={(row) => row.draft_id}
                  columns={[
                    { key: 'group_code', title: 'Group', render: (row) => row.group_code ?? '-' },
                    {
                      key: 'discipline',
                      title: 'Discipline',
                      render: (row) => row.discipline_code ?? row.discipline_name ?? '-',
                    },
                    {
                      key: 'teacher',
                      title: 'Teacher',
                      render: (row) => row.teacher_username ?? row.teacher_name ?? '-',
                    },
                    { key: 'starts_at', title: 'Начало', render: (row) => formatDateTime(row.starts_at) },
                    { key: 'ends_at', title: 'Конец', render: (row) => formatDateTime(row.ends_at) },
                    { key: 'room', title: 'Room', render: (row) => row.room ?? '-' },
                  ]}
                />
                {payload.lessons.length > 100 ? <p className="muted-small">Показаны первые 100 занятий.</p> : null}
              </Card>
            </div>
          ) : null}

          {tab === 'issues' ? (
            <Card>
              <h3>Проблемы и предупреждения</h3>
              <Table
                rows={draft.issues}
                getRowKey={(row, index) => `${row.code}-${index}` as unknown as string}
                columns={[
                  {
                    key: 'severity',
                    title: 'Severity',
                    render: (row) => <Tag variant={row.severity === 'error' ? 'danger' : row.severity === 'warning' ? 'warning' : 'default'}>{row.severity}</Tag>,
                  },
                  { key: 'code', title: 'Code', render: (row) => row.code },
                  { key: 'message', title: 'Message', render: (row) => row.message },
                  { key: 'source_ref', title: 'Source', render: (row) => row.source_ref ?? '-' },
                  { key: 'field_path', title: 'Field', render: (row) => row.field_path ?? '-' },
                ]}
              />
            </Card>
          ) : null}
        </>
      )}
    </div>
  )
}
