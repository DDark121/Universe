from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pyotp
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
_PASSWORD_SCHEME = "pbkdf2-sha256"
_PASSWORD_ROUNDS = 29_000
_PASSWORD_SALT_BYTES = 16


def _ab64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=").replace("+", ".")


def _ab64_decode(data: str) -> bytes:
    normalized = data.replace(".", "+")
    normalized += "=" * (-len(normalized) % 4)
    return base64.b64decode(normalized.encode("ascii"))


def _derive_password_hash(password: str, salt: bytes, rounds: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_PASSWORD_SALT_BYTES)
    checksum = _derive_password_hash(password, salt, _PASSWORD_ROUNDS)
    return f"${_PASSWORD_SCHEME}${_PASSWORD_ROUNDS}${_ab64_encode(salt)}${_ab64_encode(checksum)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _empty, scheme, rounds_raw, salt_raw, checksum_raw = password_hash.split("$")
        if scheme != _PASSWORD_SCHEME:
            return False
        rounds = int(rounds_raw)
        salt = _ab64_decode(salt_raw)
        checksum = _ab64_decode(checksum_raw)
    except (TypeError, ValueError):
        return False

    expected = _derive_password_hash(password, salt, rounds)
    return hmac.compare_digest(expected, checksum)


def _create_token(payload: dict[str, Any], expires_delta: timedelta) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + expires_delta
    to_encode = payload | {"exp": expires_at, "iat": datetime.now(UTC)}
    token = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def create_access_token(user_id: str, roles: list[str], password_change_required: bool) -> tuple[str, datetime]:
    return _create_token(
        {
            "sub": user_id,
            "type": "access",
            "roles": roles,
            "pwd_change_required": password_change_required,
            "jti": uuid4().hex,
        },
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str, session_id: str) -> tuple[str, datetime]:
    return _create_token(
        {"sub": user_id, "type": "refresh", "sid": session_id},
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc


def generate_session_id() -> str:
    return str(uuid4())


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_temp_password(length: int = 14) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(secret: str, username: str, issuer: str = "Universe") -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
