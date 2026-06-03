import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import type { AIImportDraftItem, AIImportMode, ImportJobItem } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { downloadBlob } from '@/shared/utils/file'
import { formatDateTime } from '@/shared/utils/format'
import { ActionChip } from '@/shared/ui/ActionChip'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { FilePickerPanel } from '@/shared/ui/FilePickerPanel'
import { Input } from '@/shared/ui/Input'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

function importStatusVariant(status: string) {
  if (status === 'done' || status === 'applied' || status === 'draft') return 'success' as const
  if (status === 'failed' || status === 'rejected') return 'danger' as const
  return 'warning' as const
}

function classicScenarioLabel(jobType: 'users' | 'schedule') {
  return jobType === 'users' ? 'Пользователи' : 'Расписание'
}

function aiModeLabel(aiMode: AIImportMode) {
  if (aiMode === 'users') return 'Только пользователи'
  if (aiMode === 'schedule') return 'Только расписание'
  return 'Смешанный документ'
}

export function ImportsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [jobType, setJobType] = useState<'users' | 'schedule'>('users')
  const [classicFile, setClassicFile] = useState<File | null>(null)

  const [aiMode, setAiMode] = useState<AIImportMode>('mixed')
  const [aiFile, setAiFile] = useState<File | null>(null)
  const [termStart, setTermStart] = useState('')
  const [termEnd, setTermEnd] = useState('')
  const [firstWeekParity, setFirstWeekParity] = useState<'odd' | 'even'>('odd')

  const jobsQuery = useQuery({
    queryKey: ['import-jobs'],
    queryFn: () => adminApi.listImports(),
    refetchInterval: 5000,
  })
  const aiDraftsQuery = useQuery({
    queryKey: ['ai-import-drafts'],
    queryFn: () => adminApi.listAIImports(),
    refetchInterval: 5000,
  })

  const classicLaunchMutation = useMutation({
    mutationFn: async ({ selectedFile, selectedType }: { selectedFile: File; selectedType: 'users' | 'schedule' }) => {
      const uploaded = await adminApi.uploadImport(selectedFile)
      return adminApi.createImportJob({
        job_type: selectedType,
        file_name: uploaded.file_name,
        file_path: uploaded.file_path,
      })
    },
    onSuccess: () => {
      setClassicFile(null)
      void queryClient.invalidateQueries({ queryKey: ['import-jobs'] })
      toast.push('Классический импорт запущен', 'success')
    },
  })

  const aiLaunchMutation = useMutation({
    mutationFn: async () => {
      if (!aiFile) {
        throw new Error('Файл не выбран')
      }
      return adminApi.createAIImportDraft({
        file: aiFile,
        mode: aiMode,
        wizard: {
          term_start: aiMode === 'users' ? null : termStart || null,
          term_end: aiMode === 'users' ? null : termEnd || null,
          first_week_parity: aiMode === 'users' ? null : firstWeekParity,
        },
      })
    },
    onSuccess: () => {
      setAiFile(null)
      if (aiMode !== 'users') {
        setTermStart('')
        setTermEnd('')
      }
      void queryClient.invalidateQueries({ queryKey: ['ai-import-drafts'] })
      toast.push('AI import draft создан', 'success')
    },
  })

  const downloadErrorsMutation = useMutation({
    mutationFn: async (job: ImportJobItem) => {
      const blob = await adminApi.downloadImportErrors(job.id)
      downloadBlob(blob, `import_errors_${job.id}.csv`)
    },
    onSuccess: () => toast.push('Отчет ошибок скачан', 'success'),
  })

  if (jobsQuery.isLoading || aiDraftsQuery.isLoading) return <Loader />

  const aiNeedsCalendar = aiMode !== 'users'
  const classicLaunchDisabled = !classicFile || classicLaunchMutation.isPending
  const aiLaunchDisabled = !aiFile || aiLaunchMutation.isPending || (aiNeedsCalendar && (!termStart || !termEnd))
  const aiDrafts = aiDraftsQuery.data ?? []
  const importJobs = jobsQuery.data ?? []

  return (
    <div className="page-grid">
      <PageTitle title="Импорт" subtitle="Классические шаблоны и AI-нормализация документов в единый draft" />

      <div className="split-grid stagger-list">
        <Card>
          <div className="control-stack">
            <div className="panel-header">
              <div>
                <div className="panel-kicker">Classic Flow</div>
                <h3>Классический импорт</h3>
                <p className="muted">Для чистых CSV/XLSX по шаблону: пользователи или расписание.</p>
              </div>
            </div>

            <div className="summary-grid">
              <div className="summary-tile">
                <span className="summary-label">Сценарий</span>
                <span className="summary-value">{classicScenarioLabel(jobType)}</span>
              </div>
              <div className="summary-tile">
                <span className="summary-label">Форматы</span>
                <span className="summary-value">CSV / XLSX</span>
              </div>
              <div className="summary-tile">
                <span className="summary-label">Поток</span>
                <span className="summary-value">Асинхронная очередь</span>
              </div>
            </div>

            <div className="field-grid-compact">
              <label className="field-stack">
                <span className="field-label">Сценарий классического импорта</span>
                <Select
                  aria-label="Сценарий классического импорта"
                  value={jobType}
                  onChange={(event) => setJobType(event.target.value as 'users' | 'schedule')}
                >
                  <option value="users">Импорт пользователей</option>
                  <option value="schedule">Импорт расписания</option>
                </Select>
              </label>
            </div>

            <FilePickerPanel
              accept=".csv,.xlsx"
              badge="Upload"
              description="Шаблон подхватится в фоне, прогресс появится ниже в classic jobs."
              file={classicFile}
              label="Файл классического импорта"
              onFileChange={setClassicFile}
            />

            <div className="toolbar-line">
              <span className="muted-small">
                {classicFile ? `Готов к запуску: ${classicFile.name}` : 'Выберите аккуратный CSV/XLSX без ручных правок формата.'}
              </span>
              <div className="toolbar-actions">
                <ActionChip
                  variant="primary"
                  disabled={classicLaunchDisabled}
                  onClick={() => {
                    if (!classicFile) return
                    classicLaunchMutation.mutate({ selectedFile: classicFile, selectedType: jobType })
                  }}
                >
                  {classicLaunchMutation.isPending ? 'Запуск...' : 'Запустить импорт'}
                </ActionChip>
              </div>
            </div>
          </div>
          {classicLaunchMutation.isError ? (
            <ErrorBlock message={getApiErrorMessage(classicLaunchMutation.error, 'Не удалось запустить импорт')} />
          ) : null}
        </Card>

        <Card>
          <div className="control-stack">
            <div className="panel-header">
              <div>
                <div className="panel-kicker">AI Flow</div>
                <h3>AI Import Wizard</h3>
                <p className="muted">Поддержка XLSX/CSV/PDF/DOCX, нормализация в редактируемый preview.</p>
              </div>
            </div>

            <div className="summary-grid">
              <div className="summary-tile">
                <span className="summary-label">Режим</span>
                <span className="summary-value">{aiModeLabel(aiMode)}</span>
              </div>
              <div className="summary-tile">
                <span className="summary-label">Календарь</span>
                <span className="summary-value">{aiNeedsCalendar ? 'Нужен семестр' : 'Не требуется'}</span>
              </div>
              <div className="summary-tile">
                <span className="summary-label">Форматы</span>
                <span className="summary-value">CSV / XLSX / PDF / DOCX</span>
              </div>
            </div>

            <div className="field-grid-compact">
              <label className="field-stack">
                <span className="field-label">Режим AI-импорта</span>
                <Select
                  aria-label="Режим AI-импорта"
                  value={aiMode}
                  onChange={(event) => setAiMode(event.target.value as AIImportMode)}
                >
                  <option value="mixed">Смешанный документ</option>
                  <option value="users">Только пользователи</option>
                  <option value="schedule">Только расписание</option>
                </Select>
              </label>
              {aiNeedsCalendar ? (
                <>
                  <label className="field-stack">
                    <span className="field-label">Дата начала семестра</span>
                    <Input
                      aria-label="Дата начала семестра"
                      type="date"
                      value={termStart}
                      onChange={(event) => setTermStart(event.target.value)}
                    />
                  </label>
                  <label className="field-stack">
                    <span className="field-label">Дата конца семестра</span>
                    <Input
                      aria-label="Дата конца семестра"
                      type="date"
                      value={termEnd}
                      onChange={(event) => setTermEnd(event.target.value)}
                    />
                  </label>
                  <label className="field-stack">
                    <span className="field-label">Четность первой недели</span>
                    <Select
                      aria-label="Четность первой недели"
                      value={firstWeekParity}
                      onChange={(event) => setFirstWeekParity(event.target.value as 'odd' | 'even')}
                    >
                      <option value="odd">Первая неделя: нечетная</option>
                      <option value="even">Первая неделя: четная</option>
                    </Select>
                  </label>
                </>
              ) : null}
            </div>

            <FilePickerPanel
              accept=".csv,.xlsx,.pdf,.docx"
              badge="AI Source"
              description="Черновик соберётся автоматически, а затем откроется в preview для ручной доводки."
              file={aiFile}
              label="Файл AI-импорта"
              onFileChange={setAiFile}
            />

            <div className="toolbar-line">
              <span className="muted-small">
                {aiNeedsCalendar
                  ? 'Для расписаний укажите рамки семестра и четность первой недели.'
                  : 'Для пользователей дополнительный календарный контекст не нужен.'}
              </span>
              <div className="toolbar-actions">
                <ActionChip variant="primary" disabled={aiLaunchDisabled} onClick={() => aiLaunchMutation.mutate()}>
                  {aiLaunchMutation.isPending ? 'Создаем draft...' : 'Создать AI draft'}
                </ActionChip>
              </div>
            </div>
          </div>
          {aiLaunchMutation.isError ? (
            <ErrorBlock message={getApiErrorMessage(aiLaunchMutation.error, 'Не удалось создать AI draft')} />
          ) : null}
        </Card>
      </div>

      <Card>
        <div className="table-card-header">
          <div>
            <div className="panel-kicker">AI Queue</div>
            <h3>AI drafts</h3>
            <p className="muted">Черновики после нормализации документа и проверки структуры.</p>
          </div>
          <div className="toolbar-actions">
            <div className="summary-tile">
              <span className="summary-label">Всего</span>
              <span className="summary-value">{aiDrafts.length}</span>
            </div>
            <ActionChip variant="quiet" onClick={() => void aiDraftsQuery.refetch()}>
              Обновить AI drafts
            </ActionChip>
          </div>
        </div>
        <Table
          rows={aiDrafts}
          getRowKey={(row: AIImportDraftItem) => row.id}
          columns={[
            { key: 'created_at', title: 'Создан', render: (row: AIImportDraftItem) => formatDateTime(row.created_at) },
            { key: 'file_name', title: 'Файл', render: (row: AIImportDraftItem) => row.file_name },
            { key: 'mode', title: 'Режим', render: (row: AIImportDraftItem) => row.mode },
            {
              key: 'status',
              title: 'Статус',
              render: (row: AIImportDraftItem) => <Tag variant={importStatusVariant(row.status)}>{row.status}</Tag>,
            },
            {
              key: 'summary',
              title: 'Сводка',
              render: (row: AIImportDraftItem) => (
                <div className="stack">
                  <span>Тип: {row.summary?.detected_doc_kind ?? '-'}</span>
                  <span className="muted-small">
                    lessons: {row.summary?.counts?.lessons ?? 0} • issues: {row.summary?.counts?.issues ?? 0}
                  </span>
                </div>
              ),
            },
            {
              key: 'actions',
              title: 'Действия',
              render: (row: AIImportDraftItem) => (
                <div className="table-inline-actions">
                  <Link className="action-chip action-chip-secondary" to={`/imports/ai/${row.id}`}>
                    Preview
                  </Link>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Card>
        <div className="table-card-header">
          <div>
            <div className="panel-kicker">Classic Queue</div>
            <h3>Classic jobs</h3>
            <p className="muted">Фоновые задачи по шаблонным CSV/XLSX-импортам.</p>
          </div>
          <div className="toolbar-actions">
            <div className="summary-tile">
              <span className="summary-label">Всего</span>
              <span className="summary-value">{importJobs.length}</span>
            </div>
            <ActionChip variant="quiet" onClick={() => void jobsQuery.refetch()}>
              Обновить classic jobs
            </ActionChip>
          </div>
        </div>
        <Table
          rows={importJobs}
          getRowKey={(row: ImportJobItem) => row.id}
          columns={[
            { key: 'created_at', title: 'Создан', render: (row: ImportJobItem) => formatDateTime(row.created_at) },
            { key: 'job_type', title: 'Тип', render: (row: ImportJobItem) => row.job_type },
            { key: 'file_name', title: 'Файл', render: (row: ImportJobItem) => row.file_name },
            {
              key: 'status',
              title: 'Статус',
              render: (row: ImportJobItem) => <Tag variant={importStatusVariant(row.status)}>{row.status}</Tag>,
            },
            {
              key: 'progress',
              title: 'Прогресс',
              render: (row: ImportJobItem) => (
                <span className="mono">
                  {row.processed_rows}/{row.total_rows || '?'}
                </span>
              ),
            },
            {
              key: 'errors',
              title: 'Ошибки',
              render: (row: ImportJobItem) =>
                row.error_report ? (
                  <div className="table-inline-actions">
                    <span className="muted-small">Есть отчет</span>
                    <ActionChip
                      variant="secondary"
                      disabled={downloadErrorsMutation.isPending}
                      onClick={() => downloadErrorsMutation.mutate(row)}
                    >
                      Скачать CSV
                    </ActionChip>
                  </div>
                ) : (
                  <span className="muted">-</span>
                ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
