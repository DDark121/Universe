import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import type { ExportJobItem } from '@/shared/api/types'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { downloadBlob } from '@/shared/utils/file'
import { formatDateTime } from '@/shared/utils/format'
import { ActionChip } from '@/shared/ui/ActionChip'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { Textarea } from '@/shared/ui/Textarea'
import { useToast } from '@/shared/ui/ToastProvider'

function exportTypeLabel(jobType: 'report' | 'risk_list') {
  return jobType === 'report' ? 'Отчет' : 'Список риска'
}

export function ExportsPage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [jobType, setJobType] = useState<'report' | 'risk_list'>('report')
  const [format, setFormat] = useState<'csv' | 'xlsx'>('xlsx')
  const [filtersJson, setFiltersJson] = useState('{\n  "report": "attendance"\n}')

  const exportsQuery = useQuery({
    queryKey: ['export-jobs'],
    queryFn: () => adminApi.listExports(),
    refetchInterval: 5000,
  })

  const createMutation = useMutation({
    mutationFn: (payload: { job_type: 'report' | 'risk_list'; format: 'csv' | 'xlsx'; filters?: Record<string, unknown> }) =>
      adminApi.createExport(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['export-jobs'] })
      toast.push('Экспорт запущен', 'success')
    },
  })

  const downloadMutation = useMutation({
    mutationFn: async (job: ExportJobItem) => {
      const blob = await adminApi.downloadExport(job.id)
      const ext = job.format === 'csv' ? 'csv' : 'xlsx'
      const filename = `export_${job.job_type}_${job.id}.${ext}`
      downloadBlob(blob, filename)
    },
    onSuccess: () => toast.push('Файл скачан', 'success'),
  })

  const launch = () => {
    let filters: Record<string, unknown> | undefined
    try {
      const parsed = JSON.parse(filtersJson)
      if (parsed && typeof parsed === 'object') {
        filters = parsed as Record<string, unknown>
      }
    } catch {
      filters = undefined
    }
    createMutation.mutate({
      job_type: jobType,
      format,
      filters,
    })
  }

  if (exportsQuery.isLoading) return <Loader />

  const exportJobs = exportsQuery.data ?? []

  return (
    <div className="page-grid">
      <PageTitle title="Экспорт" subtitle="Запуск отчетов в CSV/XLSX и скачивание результата" />

      <Card>
        <div className="control-stack">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">Export Builder</div>
              <h3>Запуск выгрузки</h3>
              <p className="muted">Соберите компактную задачу, backend положит готовый файл в очередь экспорта.</p>
            </div>
          </div>

          <div className="summary-grid">
            <div className="summary-tile">
              <span className="summary-label">Тип</span>
              <span className="summary-value">{exportTypeLabel(jobType)}</span>
            </div>
            <div className="summary-tile">
              <span className="summary-label">Формат</span>
              <span className="summary-value">{format.toUpperCase()}</span>
            </div>
            <div className="summary-tile">
              <span className="summary-label">Фильтры</span>
              <span className="summary-value">{filtersJson.trim() ? 'JSON задан' : 'Без фильтров'}</span>
            </div>
          </div>

          <div className="field-grid-compact">
            <label className="field-stack">
              <span className="field-label">Тип выгрузки</span>
              <Select value={jobType} onChange={(e) => setJobType(e.target.value as 'report' | 'risk_list')}>
                <option value="report">Отчет</option>
                <option value="risk_list">Список риска</option>
              </Select>
            </label>
            <label className="field-stack">
              <span className="field-label">Формат файла</span>
              <Select value={format} onChange={(e) => setFormat(e.target.value as 'csv' | 'xlsx')}>
                <option value="xlsx">XLSX</option>
                <option value="csv">CSV</option>
              </Select>
            </label>
          </div>

          <label className="field-stack">
            <span className="field-label">Фильтры JSON</span>
            <Textarea className="json-preview" value={filtersJson} rows={6} onChange={(e) => setFiltersJson(e.target.value)} />
          </label>

          <div className="toolbar-line">
            <span className="muted-small">Некорректный JSON будет проигнорирован и экспорт уйдет без дополнительных фильтров.</span>
            <div className="toolbar-actions">
              <ActionChip variant="primary" onClick={launch} disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Запуск...' : 'Запустить экспорт'}
              </ActionChip>
            </div>
          </div>
        </div>
        {createMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(createMutation.error, 'Не удалось запустить экспорт')} />
        ) : null}
      </Card>

      {downloadMutation.isError ? (
        <ErrorBlock message={getApiErrorMessage(downloadMutation.error, 'Не удалось скачать файл')} />
      ) : null}

      <Card>
        <div className="table-card-header">
          <div>
            <div className="panel-kicker">Export Queue</div>
            <h3>Готовые и ожидающие выгрузки</h3>
            <p className="muted">Статусы можно мониторить здесь, скачивание появится как только job завершится.</p>
          </div>
          <div className="toolbar-actions">
            <div className="summary-tile">
              <span className="summary-label">Всего</span>
              <span className="summary-value">{exportJobs.length}</span>
            </div>
            <ActionChip variant="quiet" onClick={() => void exportsQuery.refetch()}>
              Обновить
            </ActionChip>
          </div>
        </div>
        <Table
          rows={exportJobs}
          getRowKey={(row: ExportJobItem) => row.id}
          columns={[
            { key: 'created_at', title: 'Создан', render: (row: ExportJobItem) => formatDateTime(row.created_at) },
            { key: 'job_type', title: 'Тип', render: (row: ExportJobItem) => row.job_type },
            { key: 'format', title: 'Формат', render: (row: ExportJobItem) => row.format.toUpperCase() },
            {
              key: 'status',
              title: 'Статус',
              render: (row: ExportJobItem) => {
                const variant = row.status === 'done' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'
                return <Tag variant={variant}>{row.status}</Tag>
              },
            },
            {
              key: 'filters',
              title: 'Фильтры',
              render: (row: ExportJobItem) => (row.filters ? JSON.stringify(row.filters) : '-'),
            },
            {
              key: 'actions',
              title: 'Файл',
              render: (row: ExportJobItem) => (
                <ActionChip
                  variant={row.status === 'done' ? 'secondary' : 'quiet'}
                  disabled={row.status !== 'done' || downloadMutation.isPending}
                  onClick={() => downloadMutation.mutate(row)}
                >
                  Скачать
                </ActionChip>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
