from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.logging import get_logger, sanitize_log_data
from app.core.time import utc_now
from app.db.models import BiometricDevice, BiometricEvent, StudentBiometric
from app.schemas.public import (
    BiometricAttendanceRequest,
    BiometricAttendanceResponse,
    ClientErrorReportRequest,
)
from app.services.attendance import mark_attendance_by_biometric
from app.services.biometric import is_ip_allowed, verify_signature

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


def _client_error_rate_key(app_name: str, request: Request) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"client_error_rate:{app_name}:{client_ip}"


async def _allow_client_error_report(redis: Redis, *, app_name: str, request: Request) -> bool:
    key = _client_error_rate_key(app_name, request)
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        return count <= 30
    except Exception:
        return True


def _client_error_response() -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"message": "accepted"})


@router.post("/biometric/attendance", response_model=BiometricAttendanceResponse)
async def biometric_attendance_mark(
    payload: BiometricAttendanceRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    x_device_id: str = Header(alias="X-Device-Id"),
    x_timestamp: str = Header(alias="X-Timestamp"),
    x_nonce: str = Header(alias="X-Nonce"),
    x_signature: str = Header(alias="X-Signature"),
) -> BiometricAttendanceResponse:
    if not settings.biometric_public_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Biometric endpoint disabled")

    device = (
        await session.execute(
            select(BiometricDevice).where(BiometricDevice.device_id == x_device_id, BiometricDevice.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown biometric device")

    client_ip = request.client.host if request.client else None
    if not is_ip_allowed(client_ip, device.allowed_ips):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP is not allowed for device")

    try:
        ts = int(x_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timestamp header") from exc

    drift = abs(int(utc_now().timestamp()) - ts)
    if drift > settings.biometric_signature_max_drift_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Timestamp drift is too large")

    raw_body = await request.body()
    if not verify_signature(
        secret_hash=device.secret_hash,
        body=raw_body,
        timestamp=x_timestamp,
        nonce=x_nonce,
        provided=x_signature,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid biometric signature")

    nonce_key = f"biometric_nonce:{x_device_id}:{x_nonce}"
    nonce_set = await redis.set(nonce_key, "1", ex=settings.biometric_nonce_ttl_seconds, nx=True)
    if not nonce_set:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Replay detected")

    if payload.lesson_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lesson_id is required")

    existing_event = (
        await session.execute(
            select(BiometricEvent).where(
                BiometricEvent.device_id == x_device_id,
                BiometricEvent.scanner_event_id == payload.scanner_event_id,
            )
        )
    ).scalar_one_or_none()
    if existing_event and existing_event.success:
        return BiometricAttendanceResponse(
            success=True,
            reason="already_processed",
            attendance_id=None,
            student_id=existing_event.student_id,
            lesson_id=existing_event.lesson_id,
            status=None,
            marked_at=existing_event.created_at,
        )
    if existing_event and not existing_event.success:
        return BiometricAttendanceResponse(success=False, reason=existing_event.reason)

    student_bio = (
        await session.execute(
            select(StudentBiometric).where(
                StudentBiometric.fingerprint_hash == payload.fingerprint_hash,
                StudentBiometric.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not student_bio:
        session.add(
            BiometricEvent(
                device_id=x_device_id,
                scanner_event_id=payload.scanner_event_id,
                lesson_id=payload.lesson_id,
                student_id=None,
                fingerprint_hash=payload.fingerprint_hash,
                success=False,
                reason="fingerprint_not_found",
                payload=payload.model_dump(mode="json"),
            )
        )
        await session.commit()
        return BiometricAttendanceResponse(success=False, reason="fingerprint_not_found")

    try:
        record = await mark_attendance_by_biometric(
            session,
            student_id=student_bio.student_id,
            lesson_id=payload.lesson_id,
        )
        session.add(
            BiometricEvent(
                device_id=x_device_id,
                scanner_event_id=payload.scanner_event_id,
                lesson_id=payload.lesson_id,
                student_id=student_bio.student_id,
                fingerprint_hash=payload.fingerprint_hash,
                success=True,
                reason=None,
                payload=payload.model_dump(mode="json"),
            )
        )
        await session.commit()
        return BiometricAttendanceResponse(
            success=True,
            reason=None,
            attendance_id=record.id,
            student_id=record.student_id,
            lesson_id=record.lesson_id,
            status=record.status.value,
            marked_at=record.marked_at,
        )
    except HTTPException as exc:
        session.add(
            BiometricEvent(
                device_id=x_device_id,
                scanner_event_id=payload.scanner_event_id,
                lesson_id=payload.lesson_id,
                student_id=student_bio.student_id,
                fingerprint_hash=payload.fingerprint_hash,
                success=False,
                reason=str(exc.detail),
                payload=payload.model_dump(mode="json"),
            )
        )
        await session.commit()
        return BiometricAttendanceResponse(success=False, reason=str(exc.detail))


@router.post("/client-errors", status_code=status.HTTP_202_ACCEPTED)
async def report_client_error(
    payload: ClientErrorReportRequest,
    request: Request,
    redis: Redis = Depends(get_redis),
):
    correlation_id = payload.correlation_id or request.headers.get("X-Correlation-ID")
    if not await _allow_client_error_report(redis, app_name=payload.app, request=request):
        logger.warning(
            "client_error_report_dropped",
            app=payload.app,
            correlation_id=correlation_id,
            reason="rate_limited",
        )
        return _client_error_response()

    sanitized_context: dict[str, Any] | None = None
    if payload.context is not None:
        sanitized = sanitize_log_data(payload.context)
        sanitized_context = sanitized if isinstance(sanitized, dict) else {"value": sanitized}

    log_payload = {
        "app": payload.app,
        "client_level": payload.level,
        "message": payload.message,
        "stack": payload.stack,
        "url": payload.url,
        "user_agent": payload.user_agent,
        "correlation_id": correlation_id,
        "release": payload.release,
        "context": sanitized_context,
    }
    if payload.level == "warning":
        logger.warning("client_error_report", **log_payload)
    else:
        logger.error("client_error_report", **log_payload)
    return _client_error_response()
