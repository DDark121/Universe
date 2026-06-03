import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import { adminApi } from '@/shared/api/adminApi'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Loader } from '@/shared/ui/Loader'
import { PageTitle } from '@/shared/ui/PageTitle'
import { Select } from '@/shared/ui/Select'
import { Textarea } from '@/shared/ui/Textarea'
import { useToast } from '@/shared/ui/ToastProvider'

const SETTING_KEYS = [
  'attendance.default_window_start_offset_minutes',
  'attendance.default_window_duration_minutes',
  'attendance.default_late_threshold_minutes',
  'attendance.teacher_correction_window_days',
  'security.audit_retention_months',
  'localization.language',
  'auth.2fa.optional',
]

export function SettingsPage() {
  const toast = useToast()
  const [selectedKey, setSelectedKey] = useState(SETTING_KEYS[0])
  const [payloadText, setPayloadText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const settingQuery = useQuery({
    queryKey: ['setting', selectedKey],
    queryFn: () => adminApi.getSetting(selectedKey),
  })

  const updateMutation = useMutation({
    mutationFn: (value: Record<string, unknown>) => adminApi.setSetting(selectedKey, value),
    onSuccess: () => {
      toast.push('Настройка сохранена', 'success')
    },
  })

  const serverPayloadText = useMemo(
    () => JSON.stringify(settingQuery.data?.value ?? {}, null, 2),
    [settingQuery.data?.value],
  )
  const effectivePayloadText = payloadText === '' ? serverPayloadText : payloadText

  const parsedPayload = useMemo(() => {
    try {
      return JSON.parse(effectivePayloadText) as Record<string, unknown>
    } catch {
      return null
    }
  }, [effectivePayloadText])

  const onSave = async () => {
    setError(null)
    if (!parsedPayload) {
      setError('JSON невалиден')
      return
    }
    try {
      await updateMutation.mutateAsync(parsedPayload)
    } catch (e) {
      setError(getApiErrorMessage(e, 'Не удалось обновить настройку'))
    }
  }

  if (settingQuery.isLoading) {
    return <Loader />
  }

  return (
    <div className="page-grid">
      <PageTitle title="Системные настройки" subtitle="Редактор ключевых параметров backend" />

      <Card>
        <div className="form-grid">
          <Select
            value={selectedKey}
            onChange={(e) => {
              setSelectedKey(e.target.value)
              setPayloadText('')
            }}
          >
            {SETTING_KEYS.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <Card>
        <h3>Значение ключа</h3>
        <p className="muted">Формат: JSON-объект. Обычно это `{"{"}value": ...{"}"}`.</p>
        <Textarea value={effectivePayloadText} onChange={(e) => setPayloadText(e.target.value)} rows={12} />
        <div className="row-end" style={{ marginTop: 12 }}>
          <Button variant="primary" onClick={() => void onSave()} disabled={updateMutation.isPending || !parsedPayload}>
            {updateMutation.isPending ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </div>
        {error ? <ErrorBlock message={error} /> : null}
      </Card>
    </div>
  )
}
