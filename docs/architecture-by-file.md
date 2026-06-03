# Architecture By File

This repository is split into four runtime surfaces: backend API, Telegram gateway, web admin, and student mini app. The list below maps the main files that actually shape runtime behavior.

## Backend API

- `app/main.py`
  Creates the FastAPI application, configures CORS, request middleware, exception handlers, startup seed, and shutdown cleanup.
- `app/api/router.py`
  Central API namespace router. Mounts `/auth`, `/admin`, `/teacher`, `/student`, `/tg`, `/public`, and `/internal`.
- `app/api/deps.py`
  Shared FastAPI dependencies for DB sessions, auth, and role checks.

### Backend HTTP modules

- `app/api/v1/auth.py`
  Login, refresh, logout, password change, 2FA, and `/auth/me`.
- `app/api/v1/admin.py`
  Admin domain surface: users, structure, assignments, schedule, imports/exports, tutor tools, FAQ status, reports, and risk views.
- `app/api/v1/teacher.py`
  Teacher lesson, QR, attendance, reasons, reports, activity, and broadcast flows.
- `app/api/v1/student.py`
  Student profile, schedule, attendance history, warnings, FAQ, and absence reason submission.
- `app/api/v1/tg.py`
  Service-to-service API consumed by the Telegram gateway.
- `app/api/v1/public.py`
  Public client error ingestion.
- `app/api/v1/internal.py`
  Internal readiness and service checks.

### Backend infrastructure

- `app/core/config.py`
  Pydantic settings layer for backend runtime configuration.
- `app/core/db.py`
  Async SQLAlchemy engine and session factory.
- `app/core/cache.py`
  Shared Redis client factory.
- `app/core/middleware.py`
  Request correlation, logging, and exception registration.
- `app/core/security.py`
  JWT, password hashing, service token, and auth helpers.
- `app/core/pagination.py`
  Shared pagination helpers.
- `app/core/time.py`
  Date/time helpers.
- `app/core/logging.py`
  Structured logging bootstrap.

### Data model and persistence

- `app/db/models/entities.py`
  SQLAlchemy models for users, roles, groups, lessons, attendance, tutor assignments, FAQ entities, and related records.
- `app/db/enums.py`
  Shared enum definitions.
- `app/db/base.py`
  Model metadata export for Alembic and DB bootstrap.
- `app/db/seed.py`
  Idempotent initial data seeding at startup.
- `alembic/`
  Database migrations.

### Backend service layer

- `app/services/auth.py`
  Auth and token business logic.
- `app/services/attendance.py`
  Attendance window, QR generation/validation, and marking rules.
- `app/services/rating.py`
  Rating snapshot and score calculation logic.
- `app/services/escalation.py`
  Escalation thresholds, warnings, and risk automation.
- `app/services/faq_ai.py`
  Markdown-backed FAQ storage, FAISS index build/load, vector search, and assistant reply generation.
- `app/services/import_export.py`
  CSV/XLSX import/export orchestration.
- `app/services/import_apply.py`
  Row-level import application to DB entities.
- `app/services/ai_imports.py`
  AI-assisted import parsing and draft materialization.
- `app/services/storage.py`
  Attachment and file storage helpers.
- `app/services/reports.py`
  Report building logic.
- `app/services/notifications.py`
  Notification outbox and delivery orchestration.
- `app/services/activity.py`
  Teacher/student activity aggregation.
- `app/services/audit.py`
  Audit logging and retention helpers.
- `app/services/biometric.py`
  Biometric attendance verification helpers.
- `app/services/system_settings.py`
  Runtime system setting reads and cached accessors.

### Backend tasks and scripts

- `app/tasks/celery_app.py`
  Celery application bootstrap.
- `app/tasks/jobs.py`
  Background jobs for attendance, FAQ rebuilds, reports, and maintenance.
- `app/tasks/async_runner.py`
  Async helpers for running task logic from sync workers.
- `app/scripts/build_faq_index.py`
  CLI entrypoint to rebuild FAQ FAISS index.
- `app/scripts/provision_faq_embeddings.py`
  CLI entrypoint to warm the local FastEmbed cache.
- `scripts/create_service_token.py`
  CLI helper for TG service backend token generation.
- `scripts/bootstrap_demo_group_via_api.py`
  End-to-end bootstrap script for live API verification.

## Telegram Gateway

- `tg_service/main.py`
  FastAPI app plus bot runtime, command handlers, WebApp bootstrap, binding request flow, and outbound notifications.
- `tg_service/backend.py`
  Async HTTP client for backend API calls.
- `tg_service/security.py`
  Telegram init data validation and backend token verification.
- `tg_service/middleware.py`
  TG service request middleware.
- `tg_service/config.py`
  TG service settings.
- `tg_service/messages.py`
  Event message rendering.
- `tg_service/logging.py`
  TG service structured logging.
- `tg-service/Dockerfile`
  TG service image build.
- `tg-service/requirements.txt`
  TG service runtime dependencies.

## Web Admin

- `web-admin/src/main.tsx`
  Web admin entrypoint.
- `web-admin/src/app/providers.tsx`
  React Query, auth, toasts, router, and error boundary composition.
- `web-admin/src/app/router.tsx`
  Route table and lazy page registration.
- `web-admin/src/app/layout/AdminLayout.tsx`
  Shared shell for authenticated admin pages.
- `web-admin/src/app/guards.tsx`
  Route guards for auth, role access, and forced password change.

### Web Admin shared modules

- `web-admin/src/shared/api/*.ts`
  API clients, generated OpenAPI types, and domain DTOs.
- `web-admin/src/shared/auth/*.ts*`
  Session storage, route selection, and auth context.
- `web-admin/src/shared/ui/*.tsx`
  Reusable UI primitives.
- `web-admin/src/shared/utils/*.ts`
  Formatting, CSV, debounce, and file helpers.
- `web-admin/src/shared/telemetry/clientLogger.ts`
  Browser-side error reporting.
- `web-admin/src/shared/constants/menu.ts`
  Navigation model.

### Web Admin feature pages

- `web-admin/src/pages/auth/*`
  Login and password change.
- `web-admin/src/pages/dashboard/*`
  Overview dashboard.
- `web-admin/src/pages/users/*`
  User CRUD.
- `web-admin/src/pages/structure/*`
  Faculties, streams, groups, disciplines.
- `web-admin/src/pages/assignments/*`
  Teacher assignments.
- `web-admin/src/pages/tutor/*`
  Tutor assignments and tutor pushes.
- `web-admin/src/pages/schedule/*`
  Lesson planning.
- `web-admin/src/pages/telegram/*`
  Invite codes and binding requests.
- `web-admin/src/pages/faq/*`
  FAQ read-only admin views.
- `web-admin/src/pages/rating/*`
  Rating settings.
- `web-admin/src/pages/escalations/*`
  Escalation thresholds.
- `web-admin/src/pages/imports/*`
  Imports and AI import draft review.
- `web-admin/src/pages/exports/*`
  Export jobs.
- `web-admin/src/pages/reports/*`
  Attendance, lates, and absences reports.
- `web-admin/src/pages/teacher/*`
  Teacher support and moderation pages.
- `web-admin/src/pages/risk/*`
  Risk lists and student detail.
- `web-admin/src/pages/analytics/*`
  Teacher analytics.
- `web-admin/src/pages/audit/*`
  Audit log view.
- `web-admin/src/pages/settings/*`
  System settings.

## Student Mini App

- `student-app/src/main.tsx`
  Student app entrypoint.
- `student-app/src/App.tsx`
  Main Telegram mini app flow: bootstrap, student schedule/QR/reasons/FAQ, and teacher lessons/QR/attendance/reasons/broadcast UI.
- `student-app/src/telegram.ts`
  Telegram WebApp integration helpers.
- `student-app/src/clientLogger.ts`
  Browser-side telemetry for mini app failures.
- `student-app/src/ErrorBoundary.tsx`
  Runtime UI fallback.
- `student-app/src/types.ts`
  Shared client-side payload types.
- `student-app/src/styles.css`
  Global mini app styling.

## Tests

- `tests/conftest.py`
  Shared fixtures for DB, API client, and FAQ storage isolation.
- `tests/test_*`
  Backend API, service, and Telegram gateway coverage.
- `web-admin/src/**/*.test.ts*`
  Web admin unit/integration tests.
- `student-app/src/**/*.test.ts*`
  Student app unit/integration tests.
