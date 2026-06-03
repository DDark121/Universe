from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from jose import jwt

from app.core.config import get_settings

settings = get_settings()


def _build_service_token() -> str:
    payload = {
        "service": "backend",
        "target": "tg-service",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.service_token_secret, algorithm=settings.jwt_algorithm)


async def send_to_tg_service(
    telegram_id: int | None,
    event_type: str,
    payload: dict,
    idempotency_key: str,
) -> tuple[bool, dict | str]:
    if not telegram_id:
        return False, "recipient has no telegram id"

    request_payload = {
        "telegram_id": telegram_id,
        "event_type": event_type,
        "payload": payload,
        "idempotency_key": idempotency_key,
    }

    headers = {
        "X-Service-Token": _build_service_token(),
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.tg_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.tg_service_base_url}/internal/messages/send",
                json=request_payload,
                headers=headers,
            )
        if 200 <= response.status_code < 300:
            return True, response.json() if response.content else {}
        return False, response.text
    except Exception as exc:
        return False, str(exc)
