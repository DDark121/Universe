import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/shared/auth/AuthContext'
import { getDefaultRoute } from '@/shared/auth/defaultRoute'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBlock } from '@/shared/ui/ErrorBlock'
import { Input } from '@/shared/ui/Input'

type FormValues = {
  username: string
  password: string
  otp_code?: string
}

export function LoginPage() {
  const { login, isAuthenticated, session } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const { register, handleSubmit } = useForm<FormValues>({
    defaultValues: {
      username: 'admin',
      password: '',
      otp_code: '',
    },
  })

  const onSubmit = handleSubmit(async (payload) => {
    setError(null)
    setLoading(true)
    try {
      await login(payload)
    } catch {
      setError('Не удалось войти. Проверьте логин/пароль и OTP-код.')
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    if (!isAuthenticated) return
    navigate(session?.mustChangePassword ? '/password-change' : getDefaultRoute(session?.user?.roles), { replace: true })
  }, [isAuthenticated, navigate, session?.mustChangePassword, session?.user?.roles])

  return (
    <div className="login-view">
      <Card>
        <div className="login-card">
          <h2>Вход в админ-панель</h2>
          <p className="muted">Используйте учетную запись администратора, куратора или преподавателя.</p>

          <form className="page-grid" onSubmit={onSubmit}>
            <label>
              Логин
              <Input placeholder="admin" {...register('username', { required: true })} />
            </label>
            <label>
              Пароль
              <Input type="password" placeholder="Введите пароль" {...register('password', { required: true })} />
            </label>
            <label>
              OTP код (если 2FA включена)
              <Input placeholder="123456" {...register('otp_code')} />
            </label>

            {error ? <ErrorBlock message={error} /> : null}

            <Button variant="primary" disabled={loading} type="submit">
              {loading ? 'Входим...' : 'Войти'}
            </Button>
          </form>
        </div>
      </Card>
    </div>
  )
}
