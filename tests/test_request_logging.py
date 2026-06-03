from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.middleware import RequestContextMiddleware, register_exception_handlers


class _LoggerStub:
    def __init__(self):
        self.records: list[tuple[str, str, dict]] = []

    def info(self, event: str, **payload):
        self.records.append(("info", event, payload))

    def warning(self, event: str, **payload):
        self.records.append(("warning", event, payload))

    def error(self, event: str, **payload):
        self.records.append(("error", event, payload))

    def exception(self, event: str, **payload):
        self.records.append(("exception", event, payload))


@pytest.mark.asyncio
async def test_request_middleware_logs_success_and_preserves_correlation_id(monkeypatch):
    logger = _LoggerStub()
    monkeypatch.setattr("app.core.middleware.logger", logger)

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.get("/ok", headers={"X-Correlation-ID": "corr-123"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-123"
    assert logger.records[-1][0] == "info"
    assert logger.records[-1][1] == "request_completed"
    assert logger.records[-1][2]["correlation_id"] == "corr-123"


@pytest.mark.asyncio
async def test_request_middleware_logs_exceptions_and_http_warnings(monkeypatch):
    logger = _LoggerStub()
    monkeypatch.setattr("app.core.middleware.logger", logger)

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        forbidden_response = await client.get("/forbidden")
        boom_response = await client.get("/boom")

    assert forbidden_response.status_code == 403
    assert boom_response.status_code == 500
    events = [(level, event) for level, event, _payload in logger.records]
    assert ("warning", "http_exception") in events
    assert ("exception", "request_unhandled_exception") in events
    assert ("exception", "internal_exception") in events
