# Universe Web Admin

Web Admin сервис для системы учета посещаемости и дисциплины.

## Стек
- React + TypeScript + Vite
- React Router
- TanStack Query
- React Hook Form + Zod
- Axios
- Vitest + Testing Library
- Playwright

## Дизайн-токены
Обязательная палитра:
- `#0B161E`
- `#51625C`
- `#A6B9BE`
- `#D8D2C6`
- `#4F6734`

Токены и базовые стили: `src/shared/styles/global.css`.

## Запуск локально
```bash
npm install
npm run dev
```

Переменные окружения:
- `VITE_API_BASE_URL=http://localhost:8000/api/v1`

В Docker-сборке это значение берется из root `.env` через `docker-compose.yml`.

## Скрипты
- `npm run dev` - запуск dev-сервера
- `npm run build` - production build
- `npm run preview` - предпросмотр build
- `npm run lint` - eslint
- `npm run test` - unit/integration tests (vitest)
- `npm run test:e2e` - e2e smoke (playwright)
- `npm run openapi:types` - генерация OpenAPI типов

Перед первым `npm run test:e2e`:
```bash
npx playwright install chromium
```

Unexpected runtime/API failures are reported to backend endpoint `POST /api/v1/public/client-errors`.

## Docker
Сборка и запуск через root `docker-compose.yml`.
Контейнер публикуется на `http://localhost:3000`.
