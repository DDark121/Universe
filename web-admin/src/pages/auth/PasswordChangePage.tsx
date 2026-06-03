import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'

type FormValues = {
  currentPassword: string
  newPassword: string
  confirmPassword: string
}

export function PasswordChangePage() {
  const { updatePassword } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  const { register, handleSubmit } = useForm<FormValues>()

  const onSubmit = handleSubmit(async (payload) => {
    setError(null)
    setOk(null)
    if (payload.newPassword !== payload.confirmPassword) {
      setError('Новые пароли не совпадают')
      return
    }
    try {
      await updatePassword(payload.currentPassword, payload.newPassword)
      setOk('Пароль обновлен')
      navigate('/dashboard', { replace: true })
    } catch {
      setError('Не удалось изменить пароль')
    }
  })

  return (
    <div className="login-view">
      <Card>
        <h2>Смена временного пароля</h2>
        <p className="muted">Перед продолжением нужно сменить пароль.</p>
        <form className="page-grid" onSubmit={onSubmit}>
          <label>
            Текущий пароль
            <Input type="password" {...register('currentPassword', { required: true })} />
          </label>
          <label>
            Новый пароль
            <Input type="password" {...register('newPassword', { required: true, minLength: 8 })} />
          </label>
          <label>
            Повтор нового пароля
            <Input type="password" {...register('confirmPassword', { required: true })} />
          </label>
          {error ? <ErrorBlock message={error} /> : null}
          {ok ? <p className="success-text">{ok}</p> : null}
          <Button variant="primary" type="submit">
            Сохранить пароль
          </Button>
        </form>
      </Card>
    </div>
  )
}
