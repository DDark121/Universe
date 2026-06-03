.PHONY: install frontend-install lint test run migrate upgrade seed worker beat faq-index-build web-admin-dev web-admin-build web-admin-test tg-service-run student-app-dev student-app-build student-app-test student-app-docker

DOCKER ?= docker

install:
	pip install -e .[dev]

frontend-install:
	cd web-admin && npm ci
	cd student-app && npm ci

lint:
	ruff check app tests

test:
	pytest -q

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic revision --autogenerate -m "$(m)"

upgrade:
	alembic upgrade head

seed:
	python -m app.db.seed

worker:
	celery -A app.tasks.celery_app.celery_app worker -l info

beat:
	celery -A app.tasks.celery_app.celery_app beat -l info

faq-index-build:
	python -m app.scripts.build_faq_index

web-admin-dev:
	cd web-admin && npm run dev

web-admin-build:
	cd web-admin && npm run build

web-admin-test:
	cd web-admin && npm run test

tg-service-run:
	uvicorn tg_service.main:app --reload --host 0.0.0.0 --port 8080

student-app-dev:
	cd student-app && npm run dev

student-app-build:
	cd student-app && npm run build

student-app-test:
	cd student-app && npm run test

student-app-docker:
	$(DOCKER) compose up --build -d backend-api tg-service student-app
