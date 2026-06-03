from __future__ import annotations

from app.services.biometric import compute_signature, is_ip_allowed, verify_signature


def test_verify_signature_success() -> None:
    body = b'{"fingerprint_hash":"abc","lesson_id":"123"}'
    ts = "1700000000"
    nonce = "nonce-1"
    secret_hash = "device-secret-hash"
    signature = compute_signature(secret_hash=secret_hash, body=body, timestamp=ts, nonce=nonce)
    assert verify_signature(secret_hash=secret_hash, body=body, timestamp=ts, nonce=nonce, provided=signature)


def test_verify_signature_fails_on_modified_body() -> None:
    body = b'{"fingerprint_hash":"abc"}'
    tampered = b'{"fingerprint_hash":"xyz"}'
    ts = "1700000000"
    nonce = "nonce-2"
    secret_hash = "device-secret-hash"
    signature = compute_signature(secret_hash=secret_hash, body=body, timestamp=ts, nonce=nonce)
    assert not verify_signature(secret_hash=secret_hash, body=tampered, timestamp=ts, nonce=nonce, provided=signature)


def test_ip_allowlist() -> None:
    assert is_ip_allowed("10.0.0.1", ["10.0.0.1", "10.0.0.2"])
    assert not is_ip_allowed("10.0.0.3", ["10.0.0.1", "10.0.0.2"])
    assert is_ip_allowed("10.0.0.3", [])
