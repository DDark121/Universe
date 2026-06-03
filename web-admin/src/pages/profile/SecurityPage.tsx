import { useState } from 'react'

import { useAuth } from '@/shared/auth/AuthContext'
import { getApiErrorMessage } from '@/shared/utils/apiError'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'
import { PageTitle } from '@/shared/ui/PageTitle'
import { useToast } from '@/shared/ui/ToastProvider'

export function SecurityPage() {
  const { session, setup2fa, enable2fa, disable2fa } = useAuth()
  const toast = useToast()

  const [setupSecret, setSetupSecret] = useState<string | null>(null)
  const [setupUri, setSetupUri] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const onSetup = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await setup2fa()
      setSetupSecret(data.secret)
      setSetupUri(data.provisioning_uri)
      toast.push('Секрет для 2FA подготовлен', 'success')
    } catch (e) {
      setError(getApiErrorMessage(e, 'Не удалось подготовить 2FA'))
    } finally {
      setLoading(false)
    }
  }

  const onEnable = async () => {
    if (!code) {
      setError('Введите OTP-код')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await enable2fa(code)
      setCode('')
      toast.push('2FA включена', 'success')
    } catch (e) {
      setError(getApiErrorMessage(e, 'Не удалось включить 2FA'))
    } finally {
      setLoading(false)
    }
  }

  const onDisable = async () => {
    if (!code) {
      setError('Введите OTP-код')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await disable2fa(code)
      setCode('')
      setSetupSecret(null)
      setSetupUri(null)
      toast.push('2FA отключена', 'success')
    } catch (e) {
      setError(getApiErrorMessage(e, 'Не удалось отключить 2FA'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-grid">
      <PageTitle title="Профиль и безопасность" subtitle="Настройки доступа и двухфакторной аутентификации" />

      <Card>
        <div className="detail-grid">
          <div>
            <div className="muted-small">Пользователь</div>
            <div>{session?.user?.full_name ?? '-'}</div>
          </div>
          <div>
            <div className="muted-small">Логин</div>
            <div className="mono">{session?.user?.username ?? '-'}</div>
          </div>
          <div>
            <div className="muted-small">Роли</div>
            <div>{session?.user?.roles.join(', ') ?? '-'}</div>
          </div>
        </div>
      </Card>

      <Card>
        <h3>Двухфакторная аутентификация (TOTP)</h3>
        <p className="muted">Сначала получите секрет, затем подтвердите OTP-кодом из приложения.</p>

        <div className="row">
          <Button variant="primary" onClick={() => void onSetup()} disabled={loading}>
            Сгенерировать секрет
          </Button>
        </div>

        {setupSecret ? (
          <div className="stack">
            <div>
              <div className="muted-small">Секрет</div>
              <code className="code">{setupSecret}</code>
            </div>
            <div>
              <div className="muted-small">Provisioning URI</div>
              <code className="code" style={{ display: 'inline-block', maxWidth: '100%', overflowWrap: 'anywhere' }}>
                {setupUri}
              </code>
            </div>
          </div>
        ) : null}

        <div className="split-grid" style={{ marginTop: 12 }}>
          <label>
            OTP-код
            <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" maxLength={8} />
          </label>
          <div className="row-end" style={{ alignItems: 'end' }}>
            <Button variant="primary" onClick={() => void onEnable()} disabled={loading}>
              Включить 2FA
            </Button>
            <Button variant="danger" onClick={() => void onDisable()} disabled={loading}>
              Отключить 2FA
            </Button>
          </div>
        </div>

        {error ? <ErrorBlock message={error} /> : null}
      </Card>
    </div>
  )
}
