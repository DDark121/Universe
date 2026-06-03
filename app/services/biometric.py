from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable


def build_signature_payload(body: bytes, timestamp: str, nonce: str) -> bytes:
    return f"{timestamp}.{nonce}.".encode() + body


def compute_signature(secret_hash: str, body: bytes, timestamp: str, nonce: str) -> str:
    payload = build_signature_payload(body, timestamp=timestamp, nonce=nonce)
    return hmac.new(secret_hash.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(secret_hash: str, body: bytes, timestamp: str, nonce: str, provided: str) -> bool:
    expected = compute_signature(secret_hash=secret_hash, body=body, timestamp=timestamp, nonce=nonce)
    return hmac.compare_digest(expected, provided.strip().lower())


def is_ip_allowed(ip: str | None, allowed_ips: Iterable[str] | None) -> bool:
    if not allowed_ips:
        return True
    if not ip:
        return False
    normalized = {item.strip() for item in allowed_ips if item and item.strip()}
    if not normalized:
        return True
    return ip in normalized
