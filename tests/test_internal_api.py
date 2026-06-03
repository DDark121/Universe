from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_db_session
from app.main import app


class _RedisStub:
    async def ping(self) -> bool:
        return True


@pytest.fixture()
async def internal_client(session, monkeypatch):
    async def override_db():
        yield session

    app.dependency_overrides[get_db_session] = override_db
    monkeypatch.setattr("app.api.v1.internal.get_redis_client", lambda: _RedisStub())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ready_returns_ready_when_dependencies_are_operational(internal_client):
    response = await internal_client.get("/api/v1/internal/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
