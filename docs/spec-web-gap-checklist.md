# Матрица соответствия ТЗ и реализации Web Admin

Колонки:
- `Требование`
- `Канал`
- `Статус (done/partial/todo)`
- `Что уже есть`
- `Что осталось`
- `Входит в текущую итерацию`

| Требование | Канал | Статус | Что уже есть | Что осталось | Входит в текущую итерацию |
| --- | --- | --- | --- | --- | --- |
| Управление пользователями и ролями | Web Admin | `done` | CRUD пользователей, назначение ролей, RBAC | Точечные UX-улучшения | Нет |
| Учебная структура: факультеты, потоки, группы, дисциплины | Web Admin | `done` | CRUD по структуре, архивирование, назначения | Нет критичных web-gap | Нет |
| Назначения преподавателей и тьюторов | Web Admin | `done` | Teacher assignments, tutor assignments | Нет критичных web-gap | Нет |
| Расписание занятий | Web Admin | `done` | CRUD занятий, статусы, импорт расписания | Нет критичных web-gap | Нет |
| Импорт пользователей/расписания | Web Admin | `done` | Upload + async jobs + error files | Нет критичных web-gap | Нет |
| Экспорт отчетов | Web Admin | `done` | Export jobs и download | UX-полировка | Нет |
| Системные настройки | Web Admin | `done` | Настройки attendance/security/localization | Нет критичных web-gap | Нет |
| FAQ управление | Web Admin | `done` | Категории, вопросы, поиск, публикация | Нет критичных web-gap | Нет |
| Рейтинг дисциплины | Web Admin | `done` | Rating config, risk panel, карточка риска | Нет критичных web-gap | Нет |
| Эскалации и риск-панель | Web Admin | `done` | Rules, risk list, student detail, warning trigger | AI-инсайты поверх risk data | Нет |
| Аудит действий | Web Admin | `done` | Audit log screen, retention cleanup на backend | Более детальные фильтры при необходимости | Нет |
| Рассылки куратора/админа | Web Admin | `done` | Tutor broadcasts по доступным группам | Нет критичных web-gap | Нет |
| Авторизация и RBAC для преподавателя в web-admin | Web Admin | `partial` | Teacher role распознается в auth context | Teacher-specific landing, меню и routes | Да |
| Teacher cabinet: мои занятия | Web Admin | `todo` | Backend `GET /teacher/lessons` уже был | Teacher pages и обогащенный payload | Да |
| Teacher cabinet: статический QR | Web Admin | `todo` | Backend `POST /teacher/qr/generate` уже был | UI генерации и показ SVG QR | Да |
| Teacher cabinet: динамический QR | Web Admin | `todo` | Backend start/stop + WebSocket уже были | UI страницы сессии, live QR, connection state | Да |
| Teacher cabinet: ручные корректировки посещаемости | Web Admin | `todo` | Backend `POST /teacher/attendance/correct` уже был | UI roster по занятию и form reason | Да |
| Teacher cabinet: модерация причин отсутствия | Web Admin | `todo` | Backend list/moderate already existed | Teacher screen и display-данные | Да |
| Просмотр и скачивание вложений причин | Web Admin | `todo` | Хранилище и attachment records уже были | Teacher download endpoint и UI | Да |
| Teacher summary report | Web Admin | `partial` | Backend summary endpoint уже был | Teacher report screen | Да |
| Teacher detailed lates/absences report | Web Admin | `todo` | Только admin/curator reports | Отдельные teacher detailed screens | Нет |
| Teacher broadcasts | Web Admin | `todo` | Backend `POST /teacher/broadcasts` уже был | Teacher web screen | Да |
| Перевод студентов между группами | Web Admin | `partial` | Backend endpoint `/admin/student-transfer` есть | Отдельный UI в web-admin | Нет |
| AI-инсайты и рекомендации | Web Admin | `todo` | Есть risk forecast, но нет AI UI/настроек/текстов | Dashboard block, student AI card, настройки, шаблоны | Нет |
| Telegram student/teacher UX | Telegram | `partial` | Большая часть backend и tg namespace уже есть | Отдельно от текущей web-итерации | Нет |
