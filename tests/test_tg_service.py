from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest
from httpx import ASGITransport, AsyncClient

from tg_service.config import TGServiceSettings
from tg_service.main import BotService, create_app
from tg_service.messages import render_event_message
from tg_service.security import build_service_token, validate_init_data


def build_init_data(bot_token: str, *, telegram_id: int = 100500, username: str = "student") -> str:
    user_payload = json.dumps(
        {
            "id": telegram_id,
            "username": username,
            "first_name": "Test",
            "last_name": "Student",
        },
        separators=(",", ":"),
    )
    auth_date = str(int(datetime.now(UTC).timestamp()))
    pairs = {
        "auth_date": auth_date,
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": user_payload,
    }
    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(pairs)


class FakeBackend:
    def __init__(self):
        self.bootstrap_payload = {"status": "link_required"}
        self.exchange_payload = {
            "access_token": "access",
            "refresh_token": "refresh",
            "token_type": "bearer",
            "access_expires_at": "2026-03-16T00:00:00Z",
            "refresh_expires_at": "2026-03-17T00:00:00Z",
            "password_change_required": False,
            "user": {
                "id": "user-1",
                "username": "student",
                "full_name": "Test Student",
                "email": None,
                "roles": ["student"],
                "is_active": True,
                "must_change_password": False,
            },
        }
        self.created_binding_requests: list[dict] = []

    async def get_bootstrap(self, telegram_id: int) -> dict:
        return self.bootstrap_payload

    async def exchange_auth(self, telegram_id: int) -> dict:
        if isinstance(self.exchange_payload, Exception):
            raise self.exchange_payload
        return self.exchange_payload

    async def create_binding_request(self, **payload) -> dict:
        self.created_binding_requests.append(payload)
        return {"message": "Binding request submitted"}

    async def aclose(self) -> None:
        return None


class FakeBot:
    def __init__(self):
        self.messages: list[dict] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_event_message(self, telegram_id: int, event_type: str, payload: dict) -> dict:
        rendered = render_event_message(event_type, payload)
        self.messages.append(
            {
                "telegram_id": telegram_id,
                "event_type": event_type,
                "payload": payload,
                "rendered": rendered,
            }
        )
        return {"status": "sent"}


@pytest.fixture()
def tg_service_settings():
    return TGServiceSettings(
        tg_bot_token="test-token",
        service_token_secret="service-secret",
        tg_polling_enabled=False,
        student_app_url="https://student-app.example/webapp",
    )


@pytest.fixture()
async def tg_service_client(tg_service_settings):
    backend = FakeBackend()
    bot = FakeBot()
    app = create_app(settings=tg_service_settings, backend_client=backend, bot_service=bot)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, backend, bot


def test_validate_init_data_accepts_valid_payload(tg_service_settings):
    init_data = build_init_data(tg_service_settings.tg_bot_token or "test-token")
    user = validate_init_data(
        init_data,
        bot_token=tg_service_settings.tg_bot_token,
        ttl_seconds=tg_service_settings.tg_init_data_ttl_seconds,
    )
    assert user.telegram_id == 100500
    assert user.username == "student"
    assert user.full_name == "Test Student"


@pytest.mark.asyncio
async def test_webapp_bootstrap_returns_linked_tokens_and_pending_status(tg_service_client):
    client, backend, _bot = tg_service_client
    init_data = build_init_data("test-token")

    backend.bootstrap_payload = {"status": "linked", "user": {"roles": ["student"]}}
    linked_response = await client.post("/webapp/bootstrap", json={"init_data": init_data})
    assert linked_response.status_code == 200
    linked_payload = linked_response.json()
    assert linked_payload["status"] == "linked"
    assert linked_payload["tokens"]["access_token"] == "access"
    assert linked_payload["user"]["username"] == "student"

    backend.bootstrap_payload = {"status": "pending", "requested_full_name": "Queued Student"}
    pending_response = await client.post("/webapp/bootstrap", json={"init_data": init_data})
    assert pending_response.status_code == 200
    assert pending_response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_webapp_bootstrap_returns_linked_teacher_tokens(tg_service_client):
    client, backend, _bot = tg_service_client
    init_data = build_init_data("test-token", telegram_id=100800, username="teacher")

    backend.bootstrap_payload = {"status": "linked", "user": {"roles": ["teacher"]}}
    backend.exchange_payload = {
        "access_token": "teacher-access",
        "refresh_token": "teacher-refresh",
        "token_type": "bearer",
        "access_expires_at": "2026-03-16T00:00:00Z",
        "refresh_expires_at": "2026-03-17T00:00:00Z",
        "password_change_required": False,
        "user": {
            "id": "teacher-1",
            "username": "teacher",
            "full_name": "Test Teacher",
            "email": None,
            "roles": ["teacher"],
            "is_active": True,
            "must_change_password": False,
        },
    }

    response = await client.post("/webapp/bootstrap", json={"init_data": init_data})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "linked"
    assert payload["tokens"]["access_token"] == "teacher-access"
    assert payload["user"]["roles"] == ["teacher"]


@pytest.mark.asyncio
async def test_binding_request_and_internal_message_send_work(tg_service_client, tg_service_settings):
    client, backend, bot = tg_service_client
    init_data = build_init_data("test-token", telegram_id=100777, username="queued_student")

    binding = await client.post(
        "/webapp/binding-request",
        json={
            "init_data": init_data,
            "full_name": "Queued Student",
            "group_code": "SE-201",
            "note": "Need account",
        },
    )
    assert binding.status_code == 200
    assert binding.json()["status"] == "pending"
    assert backend.created_binding_requests[0]["telegram_id"] == 100777
    assert backend.created_binding_requests[0]["group_code"] == "SE-201"

    service_token = build_service_token(tg_service_settings, service="backend", target="tg-service")
    message_response = await client.post(
        "/internal/messages/send",
        headers={"X-Service-Token": service_token},
        json={
            "telegram_id": 100777,
            "event_type": "unknown_event",
            "payload": {},
            "idempotency_key": "event-1",
        },
    )
    assert message_response.status_code == 200
    assert bot.messages[0]["rendered"] == "У вас новое уведомление в системе."


@pytest.mark.asyncio
async def test_bot_service_start_deletes_webhook_before_polling(tg_service_settings):
    backend = FakeBackend()
    settings = tg_service_settings.model_copy(update={"tg_polling_enabled": True})
    service = BotService(settings, backend)
    fake_bot = AsyncMock()
    fake_dispatcher = SimpleNamespace(
        start_polling=AsyncMock(),
        resolve_used_update_types=lambda: ["message"],
    )
    service._ensure_runtime = AsyncMock(return_value=(fake_bot, fake_dispatcher))
    service._configure_menu = AsyncMock()

    await service.start()

    service._ensure_runtime.assert_awaited_once()
    fake_bot.delete_webhook.assert_awaited_once_with(
        drop_pending_updates=settings.tg_drop_pending_updates_on_start
    )
    service._configure_menu.assert_awaited_once()
    fake_dispatcher.start_polling.assert_awaited_once_with(fake_bot, allowed_updates=["message"])
