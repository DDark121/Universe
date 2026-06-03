from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

from jose import JWTError, jwt

from tg_service.config import TGServiceSettings


class InitDataValidationError(ValueError):
    pass


@dataclass(slots=True)
class TelegramWebAppUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None

    @property
    def full_name(self) -> str:
        parts = [part for part in [self.first_name, self.last_name] if part]
        return " ".join(parts).strip()


def build_service_token(settings: TGServiceSettings, *, service: str, target: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "service": service,
        "target": target,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.service_token_secret, algorithm=settings.jwt_algorithm)


def build_backend_token(settings: TGServiceSettings) -> str:
    return build_service_token(settings, service="tg-service", target="backend")


def verify_backend_token(token: str, settings: TGServiceSettings) -> dict:
    try:
        payload = jwt.decode(token, settings.service_token_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InitDataValidationError("Invalid service token") from exc

    if payload.get("service") != "backend":
        raise InitDataValidationError("Unexpected service identity")
    if payload.get("target") not in {None, "tg-service"}:
        raise InitDataValidationError("Unexpected service target")
    return payload


def validate_init_data(
    init_data: str,
    *,
    bot_token: str | None,
    ttl_seconds: int,
    now: datetime | None = None,
) -> TelegramWebAppUser:
    if not bot_token:
        raise InitDataValidationError("Telegram bot token is not configured")
    if not init_data:
        raise InitDataValidationError("init_data is required")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataValidationError("init_data hash is missing")

    auth_date_raw = pairs.get("auth_date")
    if not auth_date_raw:
        raise InitDataValidationError("auth_date is missing")

    try:
        auth_date = datetime.fromtimestamp(int(auth_date_raw), tz=UTC)
    except (TypeError, ValueError) as exc:
        raise InitDataValidationError("auth_date is invalid") from exc

    now = now or datetime.now(UTC)
    if abs((now - auth_date).total_seconds()) > ttl_seconds:
        raise InitDataValidationError("init_data is expired")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataValidationError("init_data hash mismatch")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InitDataValidationError("Telegram user payload is missing")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise InitDataValidationError("Telegram user payload is invalid") from exc

    telegram_id = user.get("id")
    if not isinstance(telegram_id, int):
        raise InitDataValidationError("Telegram user id is invalid")

    return TelegramWebAppUser(
        telegram_id=telegram_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )
