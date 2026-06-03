from __future__ import annotations

import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.core.db import get_db_session
from app.main import app


class _RedisStub:
    def __init__(self, *, count: int = 0):
        self.count = count

    async def incr(self, _key: str) -> int:
        self.count += 1
        return self.count

    async def expire(self, _key: str, _ttl: int) -> bool:
        return True


class _LoggerStub:
    def __init__(self):
        self.records: list[tuple[str, str, dict]] = []

    def warning(self, event: str, **payload):
        self.records.append(("warning", event, payload))

    def error(self, event: str, **payload):
        self.records.append(("error", event, payload))


@pytest.fixture()
async def public_client(session):
    async def override_db():
        yield session

    app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_client_error_report_is_logged_with_sanitized_context(public_client, monkeypatch):
    logger = _LoggerStub()
    redis = _RedisStub()

    async def override_redis():
        return redis

    app.dependency_overrides[get_redis] = override_redis
    monkeypatch.setattr("app.api.v1.public.logger", logger)

    response = await public_client.post(
        "/api/v1/public/client-errors",
        headers={"X-Correlation-ID": "corr-123"},
        json={
            "app": "student-app",
            "level": "error",
            "message": "UI crashed",
            "stack": "trace",
            "url": "http://localhost:3100",
            "user_agent": "test-browser",
            "context": {
                "token": "secret-token",
                "nested": {"authorization": "Bearer abc"},
            },
        },
    )

    assert response.status_code == 202
    assert logger.records[0][0] == "error"
    assert logger.records[0][1] == "client_error_report"
    payload = logger.records[0][2]
    assert payload["correlation_id"] == "corr-123"
    assert payload["context"] == {
        "token": "[redacted]",
        "nested": {"authorization": "[redacted]"},
    }


@pytest.mark.asyncio
async def test_client_error_report_is_dropped_when_rate_limited(public_client, monkeypatch):
    logger = _LoggerStub()
    redis = _RedisStub(count=30)

    async def override_redis():
        return redis

    app.dependency_overrides[get_redis] = override_redis
    monkeypatch.setattr("app.api.v1.public.logger", logger)

    response = await public_client.post(
        "/api/v1/public/client-errors",
        json={
            "app": "web-admin",
            "level": "warning",
            "message": "Slow query",
            "url": "http://localhost:3000",
            "user_agent": "test-browser",
        },
    )

    assert response.status_code == 202
    assert logger.records[0][0] == "warning"
    assert logger.records[0][1] == "client_error_report_dropped"


@pytest.mark.asyncio
async def test_cors_preflight_allows_ngrok_origin(session, monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,https://5978-89-146-66-26.ngrok-free.app",
    )
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"^https://([a-z0-9-]+\.ngrok-free\.app|[a-z0-9-]+\.ngrok\.app|[a-z0-9-]+\.ngrok\.io|[a-z0-9-]+\.trycloudflare\.com)$",
    )

    import app.core.config as config_module
    import app.main as main_module

    config_module.get_settings.cache_clear()
    main_module = importlib.reload(main_module)

    async def override_db():
        yield session

    main_module.app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(transport=ASGITransport(app=main_module.app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://5978-89-146-66-26.ngrok-free.app",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    main_module.app.dependency_overrides.clear()
    config_module.get_settings.cache_clear()

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://5978-89-146-66-26.ngrok-free.app"
    assert response.headers["access-control-allow-credentials"] == "true"
