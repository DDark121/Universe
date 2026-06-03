# Universe Backend

Backend for the student attendance and discipline system.

## Stack
- FastAPI (REST, OpenAPI)
- PostgreSQL (SQLAlchemy 2 + Alembic)
- Redis + Celery (worker + beat)
- React + TypeScript + Vite (Web Admin)
- Docker Compose deployment

## Services
- `backend-api`: FastAPI HTTP API
- `backend-worker`: Celery worker
- `backend-beat`: Celery scheduler
- `tg-service`: Telegram bot + mini app gateway
- `web-admin`: React admin panel (Nginx static runtime)
- `student-app`: React Telegram mini app for students and teachers
- `postgres`: primary database
- `redis`: broker/cache/rate-limit store

## Quick Start
1. Copy env:
```bash
cp .env.example .env
```
`.env.example` now contains backend, Telegram gateway, and frontend build variables, including `VITE_API_BASE_URL` and `VITE_TG_SERVICE_BASE_URL`.
2. Build and run:
```bash
docker compose up --build -d
```
3. Apply migrations:
```bash
docker compose exec backend-api alembic upgrade head
```
4. Open docs:
- `http://localhost:8000/docs`
5. Open web admin:
- `http://localhost:3000/login`
6. Open student mini app preview:
- `http://localhost:3100`
7. Telegram gateway health:
- `http://localhost:8080/health`

## Local Commands
```bash
make install
make lint
make test
make run
make upgrade
make seed
make worker
make beat
make tg-service-run
make web-admin-dev
make web-admin-build
make web-admin-test
make student-app-dev
make student-app-build
make student-app-test
```

## FAQ / FAISS Knowledge Base
- FAQ source files live in `data/**/*.md`. Each markdown file becomes one FAQ item, and the parent folder becomes its category.
- The repository now includes a demo knowledge base for ТГТУ with admissions, study process, dormitory, stipend, military registration, digital services, and session questions.
- To prepare embeddings cache on a clean machine:
```bash
uv run python -m app.scripts.provision_faq_embeddings
```
- To rebuild the FAISS index from the markdown knowledge base:
```bash
uv run python -m app.scripts.build_faq_index
```

Frontend browser smoke:
```bash
cd web-admin && npx playwright install chromium && npm run test:e2e
cd student-app && npx playwright install chromium && npm run test:e2e
```

## Service Token Helper
Generate internal S2S token (for tg-service -> backend calls):
```bash
python3 scripts/create_service_token.py --secret \"$SERVICE_TOKEN_SECRET\" --service tg-service
```

## Default Seed Data
- Admin user: `admin`
- Temporary password: `Admin123!` (must be changed after first login)

## API Namespaces
- `/api/v1/auth/*`
- `/api/v1/admin/*`
- `/api/v1/teacher/*`
- `/api/v1/student/*`
- `/api/v1/tg/*`
- `/api/v1/internal/*`
- `/api/v1/public/client-errors`

## Web Admin
- Path: `web-admin/`
- Default API base URL in Docker: `http://backend-api:8000/api/v1`
- Unexpected runtime/API failures are reported to `POST /api/v1/public/client-errors` with `X-Correlation-ID`
- Local dev:
```bash
cd web-admin
npm install
npm run dev
```

## Student Mini App
- Path: `student-app/`
- Telegram gateway path: `tg_service/` and deployment files in `tg-service/`
- Public entrypoint for Telegram should be only the student app URL.
- Inside `student-app` nginx, requests to `/tg/*` are proxied to `tg-service`, and `/api/*` are proxied to `backend-api`.
- Unexpected runtime/API failures are reported to `POST /api/v1/public/client-errors` with `X-Correlation-ID`
- Local dev server listens on `http://localhost:3100`
- Local dev:
```bash
cd student-app
npm install
npm run dev
```
- Docker preview on port `3100`:
```bash
make student-app-docker
```
- If your user does not have access to `/var/run/docker.sock`, run:
```bash
make student-app-docker DOCKER="sudo docker"
```
- Do not run `npm run dev` for `student-app` at the same time as the Docker preview, because both use port `3100`
- Cloudflare tunnel should target `http://localhost:3100`
- `STUDENT_APP_URL` in `.env` should be the public tunnel URL that Telegram opens, not `http://localhost:3100`

## Staging Smoke
- Checklist: [docs/staging-smoke-checklist.md](/home/danila/Universe/docs/staging-smoke-checklist.md)

## Key Implemented Features
- JWT access/refresh auth with refresh rotation
- Optional TOTP 2FA
- RBAC (`student`, `teacher`, `admin`, `curator`)
- `curator` role is displayed as «Тьютор» in Web Admin
- Telegram binding via invite code and manual request workflow
- Attendance by static and dynamic QR (3s rotation via WebSocket) with anti-fraud checks
- Public biometric attendance endpoint with device HMAC signature + anti-replay nonce
- Auto-absence after attendance window closes
- Teacher manual correction window (3 days)
- Absence reasons + moderation + attachment upload
- Notification outbox + delivery retries (Celery) + lesson window triggers
- Rating snapshots + escalation events + risk cards + 14/28 day risk forecast
- FAQ management and search
- Full async import/export pipelines (CSV/XLSX, error reports, template download)
- Audit logs + retention cleanup job

## Tests
Run:
```bash
python3 -m pytest -q
```
Current suite validates:
- auth login/refresh/logout flow
- QR attendance marking and duplicate protection
- auto-absence behavior
- rating snapshot recalculation
