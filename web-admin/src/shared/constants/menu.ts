import type { RoleCode } from '@/shared/api/types'

export type MenuItem = {
  label: string
  to: string
  roles: RoleCode[]
}

export type MenuSection = {
  title: string
  items: MenuItem[]
}

export const MENU: MenuSection[] = [
  {
    title: 'Обзор',
    items: [
      { label: 'Дашборд', to: '/dashboard', roles: ['admin', 'curator'] },
      { label: 'Профиль и 2FA', to: '/profile/security', roles: ['admin', 'curator', 'teacher'] },
    ],
  },
  {
    title: 'Преподаватель',
    items: [
      { label: 'Мои занятия', to: '/teacher/lessons', roles: ['teacher'] },
      { label: 'Причины отсутствия', to: '/teacher/absence-reasons', roles: ['teacher'] },
      { label: 'Отчет посещаемости', to: '/teacher/reports', roles: ['teacher'] },
      { label: 'Рассылки преподавателя', to: '/teacher/broadcasts', roles: ['teacher'] },
    ],
  },
  {
    title: 'Управление',
    items: [
      { label: 'Пользователи', to: '/users', roles: ['admin'] },
      { label: 'Факультеты', to: '/structure/faculties', roles: ['admin'] },
      { label: 'Потоки', to: '/structure/streams', roles: ['admin'] },
      { label: 'Группы', to: '/structure/groups', roles: ['admin'] },
      { label: 'Дисциплины', to: '/structure/disciplines', roles: ['admin'] },
      { label: 'Назначения', to: '/assignments', roles: ['admin'] },
      { label: 'Назначения тьюторов', to: '/tutor/assignments', roles: ['admin'] },
      { label: 'Расписание', to: '/schedule', roles: ['admin'] },
      { label: 'Инвайт-коды TG', to: '/telegram/invites', roles: ['admin'] },
      { label: 'Привязки TG', to: '/telegram/binding-requests', roles: ['admin'] },
      { label: 'Системные настройки', to: '/settings', roles: ['admin'] },
    ],
  },
  {
    title: 'Контент и правила',
    items: [
      { label: 'FAQ категории', to: '/faq/categories', roles: ['admin'] },
      { label: 'FAQ вопросы', to: '/faq/items', roles: ['admin'] },
      { label: 'Конфиг рейтинга', to: '/rating/config', roles: ['admin'] },
      { label: 'Правила эскалаций', to: '/escalations/rules', roles: ['admin'] },
    ],
  },
  {
    title: 'Аналитика',
    items: [
      { label: 'Зона риска', to: '/risk', roles: ['admin', 'curator'] },
      { label: 'Отчет посещаемости', to: '/reports/attendance', roles: ['admin', 'curator'] },
      { label: 'Отчет опозданий', to: '/reports/lates', roles: ['admin', 'curator'] },
      { label: 'Отчет пропусков', to: '/reports/absences', roles: ['admin', 'curator'] },
      { label: 'Аналитика преподавателей', to: '/analytics/teachers', roles: ['admin', 'curator'] },
    ],
  },
  {
    title: 'Операции',
    items: [
      { label: 'Рассылки тьютора', to: '/tutor/pushes', roles: ['admin', 'curator'] },
      { label: 'Импорт', to: '/imports', roles: ['admin'] },
      { label: 'Экспорт', to: '/exports', roles: ['admin', 'curator'] },
      { label: 'Аудит', to: '/audit', roles: ['admin'] },
    ],
  },
]
