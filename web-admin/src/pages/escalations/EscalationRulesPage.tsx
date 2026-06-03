import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'

import { adminApi } from '@/shared/api/adminApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Table } from '@/shared/ui/Table'
import { Tag } from '@/shared/ui/Tag'
import { useToast } from '@/shared/ui/ToastProvider'

type RuleForm = {
  name: string
  threshold_unexcused_absences: number
  threshold_lates: number
  min_rating: number
  is_active: boolean
}

type RuleRow = {
  id: string
  name: string
  threshold_unexcused_absences: number
  threshold_lates: number
  min_rating: number
  is_active: boolean
}

export function EscalationRulesPage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const query = useQuery({ queryKey: ['escalation-rules'], queryFn: () => adminApi.listEscalationRules() })

  const createMutation = useMutation({
    mutationFn: (payload: RuleForm) => adminApi.createEscalationRule(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['escalation-rules'] })
      toast.push('Правило создано', 'success')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<RuleForm> }) => adminApi.updateEscalationRule(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['escalation-rules'] })
      toast.push('Правило обновлено', 'success')
    },
  })

  const form = useForm<RuleForm>({
    defaultValues: {
      name: '',
      threshold_unexcused_absences: 3,
      threshold_lates: 4,
      min_rating: 60,
      is_active: true,
    },
  })

  const onSubmit = form.handleSubmit(async (payload) => {
    await createMutation.mutateAsync(payload)
    form.reset({
      name: '',
      threshold_unexcused_absences: 3,
      threshold_lates: 4,
      min_rating: 60,
      is_active: true,
    })
  })

  if (query.isLoading) return <Loader />

  return (
    <div className="page-grid">
      <PageTitle title="Правила эскалаций" subtitle="Пороговые условия для предупреждений и риск-карточек" />

      <Card>
        <h3>Новое правило</h3>
        <form className="form-grid" onSubmit={onSubmit}>
          <input className="input" placeholder="Название" {...form.register('name', { required: true })} />
          <label>
            Неуважительных пропусков
            <input
              className="input"
              type="number"
              min={0}
              {...form.register('threshold_unexcused_absences', { valueAsNumber: true, required: true })}
            />
          </label>
          <label>
            Опозданий
            <input
              className="input"
              type="number"
              min={0}
              {...form.register('threshold_lates', { valueAsNumber: true, required: true })}
            />
          </label>
          <label>
            Минимальный рейтинг
            <input
              className="input"
              type="number"
              min={0}
              max={100}
              {...form.register('min_rating', { valueAsNumber: true, required: true })}
            />
          </label>
          <label className="row" style={{ alignItems: 'center' }}>
            <input type="checkbox" {...form.register('is_active')} />
            Активно
          </label>
          <Button variant="primary" type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Сохраняем...' : 'Создать'}
          </Button>
        </form>
        {createMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(createMutation.error, 'Не удалось создать правило')} />
        ) : null}
      </Card>

      <Card>
        <Table
          rows={query.data ?? []}
          getRowKey={(row: RuleRow) => row.id}
          columns={[
            { key: 'name', title: 'Правило', render: (row: RuleRow) => row.name },
            {
              key: 'thresholds',
              title: 'Пороги',
              render: (row: RuleRow) => (
                <div className="stack">
                  <span>Неуважительные: {row.threshold_unexcused_absences}</span>
                  <span>Опоздания: {row.threshold_lates}</span>
                  <span>Рейтинг &lt; {row.min_rating}</span>
                </div>
              ),
            },
            {
              key: 'status',
              title: 'Статус',
              render: (row: RuleRow) => <Tag variant={row.is_active ? 'success' : 'warning'}>{row.is_active ? 'Активно' : 'Отключено'}</Tag>,
            },
            {
              key: 'actions',
              title: 'Действия',
              render: (row: RuleRow) => (
                <div className="row">
                  <Button
                    onClick={() => {
                      const nextName = prompt('Новое имя правила', row.name)
                      if (nextName && nextName.trim()) {
                        updateMutation.mutate({ id: row.id, payload: { name: nextName.trim() } })
                      }
                    }}
                  >
                    Переименовать
                  </Button>
                  <Button
                    onClick={() => {
                      const nextMinRating = prompt('Новый порог рейтинга', String(row.min_rating))
                      if (!nextMinRating) return
                      const parsed = Number(nextMinRating)
                      if (Number.isFinite(parsed)) {
                        updateMutation.mutate({ id: row.id, payload: { min_rating: parsed } })
                      }
                    }}
                  >
                    Порог рейтинга
                  </Button>
                  <Button
                    variant={row.is_active ? 'danger' : 'primary'}
                    onClick={() => updateMutation.mutate({ id: row.id, payload: { is_active: !row.is_active } })}
                  >
                    {row.is_active ? 'Отключить' : 'Включить'}
                  </Button>
                </div>
              ),
            },
          ]}
        />

        {updateMutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(updateMutation.error, 'Не удалось обновить правило')} />
        ) : null}
      </Card>
    </div>
  )
}
