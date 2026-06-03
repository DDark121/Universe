import { Link } from 'react-router-dom'

import { Card } from '@/shared/ui/Card'

export function NotFoundPage() {
  return (
    <div className="page-grid">
      <Card>
        <h2>Страница не найдена</h2>
        <p className="muted">Проверьте адрес или вернитесь в панель управления.</p>
        <Link className="link-btn" to="/dashboard">
          На дашборд
        </Link>
      </Card>
    </div>
  )
}
