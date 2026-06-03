import { useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'

import { adminApi } from '@/shared/api/adminApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { useToast } from '@/shared/ui/ToastProvider'

type FormValues = {
  attendance_weight: number
  late_weight: number
  unexcused_absence_weight: number
  activity_weight: number
}

export function RatingConfigPage() {
  const toast = useToast()

  const query = useQuery({ queryKey: ['rating-config'], queryFn: () => adminApi.getRatingConfig() })
  const mutation = useMutation({
    mutationFn: (payload: FormValues) => adminApi.updateRatingConfig(payload),
    onSuccess: () => {
      toast.push('Конфиг рейтинга обновлен', 'success')
    },
  })

  const form = useForm<FormValues>({
    defaultValues: {
      attendance_weight: 50,
      late_weight: 20,
      unexcused_absence_weight: 30,
      activity_weight: 0,
    },
  })

  useEffect(() => {
    if (query.data) {
      form.reset({
        attendance_weight: query.data.attendance_weight,
        late_weight: query.data.late_weight,
        unexcused_absence_weight: query.data.unexcused_absence_weight,
        activity_weight: query.data.activity_weight,
      })
    }
  }, [query.data, form])

  const onSubmit = form.handleSubmit(async (payload) => {
    await mutation.mutateAsync(payload)
  })

  if (query.isLoading) return <Loader />

  return (
    <div className="page-grid">
      <PageTitle title="Конфиг рейтинга" subtitle="Веса параметров скоринга студентов" />

      <Card>
        <form className="form-grid" onSubmit={onSubmit}>
          <label>
            Посещаемость (%)
            <input className="input" type="number" step="0.1" {...form.register('attendance_weight', { valueAsNumber: true })} />
          </label>
          <label>
            Опоздания (%)
            <input className="input" type="number" step="0.1" {...form.register('late_weight', { valueAsNumber: true })} />
          </label>
          <label>
            Неуважительные пропуски (%)
            <input
              className="input"
              type="number"
              step="0.1"
              {...form.register('unexcused_absence_weight', { valueAsNumber: true })}
            />
          </label>
          <label>
            Активность (%)
            <input className="input" type="number" step="0.1" {...form.register('activity_weight', { valueAsNumber: true })} />
          </label>

          <Button variant="primary" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Сохраняем...' : 'Сохранить'}
          </Button>
        </form>

        {mutation.isError ? (
          <ErrorBlock message={getApiErrorMessage(mutation.error, 'Не удалось сохранить конфиг')} />
        ) : null}
      </Card>
    </div>
  )
}
