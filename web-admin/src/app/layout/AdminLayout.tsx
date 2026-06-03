import { NavLink, Outlet } from 'react-router-dom'

import { MENU } from '@/shared/constants/menu'
import { useAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/ui/Button'

export function AdminLayout() {
  const { session, roles, logout } = useAuth()
  const roleLabel = (role: string) => (role === 'curator' ? 'Тьютор' : role)

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-title">Universe Web Admin</div>
        {MENU.map((section) => {
          const items = section.items.filter((item) => item.roles.some((role) => roles.includes(role)))
          if (!items.length) return null
          return (
            <div key={section.title} className="nav-section">
              <div className="nav-section-title">{section.title}</div>
              {items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                >
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          )
        })}
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div>
            <strong>{session?.user?.full_name ?? '-'}</strong>
            <div className="muted">{session?.user?.roles.map(roleLabel).join(', ') ?? '-'}</div>
          </div>
          <Button variant="secondary" onClick={() => void logout()}>
            Выйти
          </Button>
        </header>

        <main className="page-wrap">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
