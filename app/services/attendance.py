from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utc_now
from app.db.enums import AttendanceSource, AttendanceStatus, ModerationStatus
from app.db.models import (
    AbsenceReason,
    AttendanceRecord,
    Lesson,
    QRSession,
    QRToken,
    StudentGroupMembership,
    TelegramAccount,
)
from app.services.audit import log_audit
from app.services.notifications import enqueue_notification

settings = get_settings()
_QR_DEEPLINK_PARAM_NAMES = ("start", "startapp", "startattach")


@dataclass(slots=True)
class _ResolvedQR:
    lesson: Lesson
    dynamic_token_hash: str | None = None
    dynamic_token_expires_at: datetime | None = None
    dynamic_created_by: UUID | None = None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _lesson_window(lesson: Lesson):
    starts_at = _as_utc(lesson.starts_at)
    start = starts_at + timedelta(minutes=lesson.window_start_offset_minutes)
    end = start + timedelta(minutes=lesson.window_duration_minutes)
    return start, end


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _qr_dynamic_secret() -> str:
    return settings.qr_dynamic_token_secret or settings.jwt_secret


def _strip_qr_prefix(value: str) -> str:
    return value[3:] if value.startswith("qr_") else value


def _deeplink_qr_token(value: str) -> str | None:
    candidates: list[str] = []
    if value.startswith("?") and len(value) > 1:
        candidates.append(value[1:])
    if value.startswith(_QR_DEEPLINK_PARAM_NAMES):
        candidates.append(value)
    query_index = value.find("?")
    if query_index >= 0 and query_index < len(value) - 1:
        candidates.append(value[query_index + 1 :])

    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
    except ValueError:
        parsed = None
    if parsed and parsed.query:
        candidates.append(parsed.query)

    for query in candidates:
        params = parse_qs(query, keep_blank_values=False)
        for key in _QR_DEEPLINK_PARAM_NAMES:
            token_values = params.get(key)
            if token_values:
                token = token_values[0].strip()
                if token:
                    return token
    return None


def _normalize_qr_token_input(qr_token: str) -> str:
    token = (qr_token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR token is empty")

    deeplink_token = _deeplink_qr_token(token)
    if deeplink_token:
        token = deeplink_token

    token = _strip_qr_prefix(token)
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR token is empty")
    return token


async def generate_qr_token(session: AsyncSession, lesson_id: UUID, teacher_id: UUID) -> tuple[str, QRToken]:
    lesson_stmt = select(Lesson).where(Lesson.id == lesson_id, Lesson.teacher_id == teacher_id)
    lesson = (await session.execute(lesson_stmt)).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    _, window_end = _lesson_window(lesson)

    deactivate_stmt = select(QRToken).where(QRToken.lesson_id == lesson_id, QRToken.is_active.is_(True))
    active_tokens = (await session.execute(deactivate_stmt)).scalars().all()
    for token in active_tokens:
        token.is_active = False

    raw = secrets.token_urlsafe(24)
    token = QRToken(
        lesson_id=lesson_id,
        token_hash=_hash_token(raw),
        expires_at=window_end,
        is_active=True,
        created_by=teacher_id,
    )
    session.add(token)
    await log_audit(
        session,
        actor_user_id=teacher_id,
        action="attendance.qr_generate",
        entity_type="lesson",
        entity_id=str(lesson_id),
    )
    await session.commit()
    await session.refresh(token)
    return raw, token


async def create_dynamic_qr_session(session: AsyncSession, lesson_id: UUID, teacher_id: UUID) -> QRSession:
    lesson = (
        await session.execute(select(Lesson).where(Lesson.id == lesson_id, Lesson.teacher_id == teacher_id))
    ).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    _, window_end = _lesson_window(lesson)
    if utc_now() > window_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance window is closed")

    active_sessions = (
        await session.execute(
            select(QRSession).where(QRSession.lesson_id == lesson_id, QRSession.is_active.is_(True))
        )
    ).scalars().all()
    for row in active_sessions:
        row.is_active = False
        row.stopped_at = utc_now()

    qr_session = QRSession(
        lesson_id=lesson_id,
        teacher_id=teacher_id,
        is_active=True,
        started_at=utc_now(),
        expires_at=window_end,
        last_slot_index=0,
    )
    session.add(qr_session)
    await session.commit()
    await session.refresh(qr_session)

    await log_audit(
        session,
        actor_user_id=teacher_id,
        action="attendance.dynamic_qr_session_start",
        entity_type="qr_session",
        entity_id=str(qr_session.id),
        details={"lesson_id": str(lesson_id)},
    )
    await session.commit()
    return qr_session


async def stop_dynamic_qr_session(session: AsyncSession, session_id: UUID, teacher_id: UUID) -> QRSession:
    row = (
        await session.execute(
            select(QRSession).where(
                QRSession.id == session_id,
                QRSession.teacher_id == teacher_id,
                QRSession.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QR session not found")

    row.is_active = False
    row.stopped_at = utc_now()
    await log_audit(
        session,
        actor_user_id=teacher_id,
        action="attendance.dynamic_qr_session_stop",
        entity_type="qr_session",
        entity_id=str(session_id),
    )
    await session.commit()
    await session.refresh(row)
    return row


def build_dynamic_qr_token(qr_session: QRSession) -> tuple[str, int]:
    slot_seconds = max(1, settings.qr_dynamic_slot_seconds)
    now = utc_now()
    slot_index = int(now.timestamp()) // slot_seconds
    payload = {
        "type": "lesson_qr_dynamic",
        "lesson_id": str(qr_session.lesson_id),
        "session_id": str(qr_session.id),
        "slot_index": slot_index,
        "jti": secrets.token_urlsafe(12),
        "iat": now,
        "exp": now + timedelta(seconds=slot_seconds),
    }
    token = jwt.encode(payload, _qr_dynamic_secret(), algorithm=settings.jwt_algorithm)
    return token, slot_index


async def _resolve_dynamic_qr_lesson(session: AsyncSession, qr_token: str) -> _ResolvedQR | None:
    if "." not in qr_token:
        return None

    try:
        payload = jwt.decode(
            qr_token,
            _qr_dynamic_secret(),
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
    except JWTError:
        return None

    if payload.get("type") != "lesson_qr_dynamic":
        return None

    lesson_id_raw = payload.get("lesson_id")
    session_id_raw = payload.get("session_id")
    slot_index = payload.get("slot_index")
    if not lesson_id_raw or not session_id_raw or slot_index is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed dynamic QR token")

    try:
        lesson_id = UUID(str(lesson_id_raw))
        session_id = UUID(str(session_id_raw))
        token_slot_index = int(slot_index)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed dynamic QR token") from exc

    qr_session = (
        await session.execute(
            select(QRSession).where(
                QRSession.id == session_id,
                QRSession.lesson_id == lesson_id,
                QRSession.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not qr_session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR session is inactive")

    now = utc_now()
    if now > _as_utc(qr_session.expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR session expired")

    slot_seconds = max(1, settings.qr_dynamic_slot_seconds)
    grace_slots = max(0, settings.qr_dynamic_grace_slots)
    now_slot_index = int(now.timestamp()) // slot_seconds
    if token_slot_index > now_slot_index + 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR token is not valid yet")
    if (now_slot_index - token_slot_index) > grace_slots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR token expired")

    qr_session.last_slot_index = max(qr_session.last_slot_index, token_slot_index)

    lesson = (await session.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    dynamic_token_lifetime = timedelta(seconds=slot_seconds * (grace_slots + 1))
    return _ResolvedQR(
        lesson=lesson,
        dynamic_token_hash=_hash_token(qr_token),
        dynamic_token_expires_at=min(_as_utc(qr_session.expires_at), now + dynamic_token_lifetime),
        dynamic_created_by=qr_session.teacher_id,
    )


async def _resolve_static_qr_lesson(session: AsyncSession, qr_token: str) -> _ResolvedQR:
    token_hash = _hash_token(qr_token)
    token_stmt = select(QRToken).where(
        QRToken.token_hash == token_hash,
        QRToken.is_active.is_(True),
        QRToken.expires_at >= utc_now(),
    )
    token_row = (await session.execute(token_stmt)).scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR token is invalid or expired")

    lesson_stmt = select(Lesson).where(Lesson.id == token_row.lesson_id)
    lesson = (await session.execute(lesson_stmt)).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return _ResolvedQR(lesson=lesson)


async def _resolve_lesson_by_qr_token(session: AsyncSession, qr_token: str) -> _ResolvedQR:
    resolved = await _resolve_dynamic_qr_lesson(session, qr_token)
    if resolved:
        return resolved
    return await _resolve_static_qr_lesson(session, qr_token)


async def _mark_student_attendance(
    session: AsyncSession,
    lesson: Lesson,
    student_id: UUID,
    source: AttendanceSource,
    recipient_telegram_id: int | None = None,
    qr_resolution: _ResolvedQR | None = None,
) -> AttendanceRecord:
    now = utc_now()
    window_start, window_end = _lesson_window(lesson)
    if not (window_start <= now <= window_end):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance window is closed")

    membership_stmt = select(StudentGroupMembership).where(
        StudentGroupMembership.student_id == student_id,
        StudentGroupMembership.group_id == lesson.group_id,
        StudentGroupMembership.start_date <= now.date(),
        or_(
            StudentGroupMembership.end_date.is_(None),
            StudentGroupMembership.end_date >= now.date(),
        ),
    )
    membership = (await session.execute(membership_stmt)).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student is not in lesson group")

    attendance_stmt = select(AttendanceRecord).where(
        AttendanceRecord.lesson_id == lesson.id,
        AttendanceRecord.student_id == student_id,
    )
    existing = (await session.execute(attendance_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already marked")

    if qr_resolution and qr_resolution.dynamic_token_hash:
        used_token = (
            await session.execute(select(QRToken.id).where(QRToken.token_hash == qr_resolution.dynamic_token_hash))
        ).scalar_one_or_none()
        if used_token:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="QR token already used")
        session.add(
            QRToken(
                lesson_id=lesson.id,
                token_hash=qr_resolution.dynamic_token_hash,
                expires_at=qr_resolution.dynamic_token_expires_at or window_end,
                is_active=False,
                created_by=qr_resolution.dynamic_created_by or lesson.teacher_id,
            )
        )

    late_deadline = _as_utc(lesson.starts_at) + timedelta(minutes=lesson.late_threshold_minutes)
    attendance_status = AttendanceStatus.LATE if now > late_deadline else AttendanceStatus.PRESENT
    record = AttendanceRecord(
        lesson_id=lesson.id,
        student_id=student_id,
        status=attendance_status,
        source=source,
        marked_at=now,
    )
    session.add(record)

    await enqueue_notification(
        session,
        event_type="attendance_marked",
        recipient_user_id=student_id,
        recipient_telegram_id=recipient_telegram_id,
        payload={"lesson_id": str(lesson.id), "status": attendance_status.value},
        idempotency_key=f"attendance_marked:{lesson.id}:{student_id}",
    )
    if attendance_status == AttendanceStatus.LATE:
        await enqueue_notification(
            session,
            event_type="attendance_late_detected",
            recipient_user_id=student_id,
            recipient_telegram_id=recipient_telegram_id,
            payload={"lesson_id": str(lesson.id), "status": attendance_status.value},
            idempotency_key=f"attendance_late_detected:{lesson.id}:{student_id}",
        )

    await session.commit()
    await session.refresh(record)
    return record


async def mark_attendance_by_qr(
    session: AsyncSession,
    telegram_id: int,
    qr_token: str,
) -> AttendanceRecord:
    qr_token = _normalize_qr_token_input(qr_token)

    account_stmt = select(TelegramAccount).where(TelegramAccount.telegram_id == telegram_id)
    account = (await session.execute(account_stmt)).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram account is not linked")

    return await mark_attendance_by_student_qr(
        session,
        student_id=account.user_id,
        qr_token=qr_token,
        recipient_telegram_id=telegram_id,
    )


async def mark_attendance_by_student_qr(
    session: AsyncSession,
    student_id: UUID,
    qr_token: str,
    recipient_telegram_id: int | None = None,
) -> AttendanceRecord:
    qr_token = _normalize_qr_token_input(qr_token)

    qr_resolution = await _resolve_lesson_by_qr_token(session, qr_token)
    lesson = qr_resolution.lesson
    if recipient_telegram_id is None:
        recipient_telegram_id = (
            await session.execute(select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == student_id))
        ).scalar_one_or_none()

    return await _mark_student_attendance(
        session,
        lesson=lesson,
        student_id=student_id,
        source=AttendanceSource.QR,
        recipient_telegram_id=recipient_telegram_id,
        qr_resolution=qr_resolution,
    )


async def mark_attendance_by_button(
    session: AsyncSession,
    *,
    student_id: UUID,
    lesson_id: UUID,
    recipient_telegram_id: int | None = None,
) -> AttendanceRecord:
    lesson = (await session.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    if recipient_telegram_id is None:
        recipient_telegram_id = (
            await session.execute(select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == student_id))
        ).scalar_one_or_none()

    return await _mark_student_attendance(
        session,
        lesson=lesson,
        student_id=student_id,
        source=AttendanceSource.BUTTON,
        recipient_telegram_id=recipient_telegram_id,
    )


async def mark_attendance_by_biometric(
    session: AsyncSession,
    student_id: UUID,
    lesson_id: UUID,
) -> AttendanceRecord:
    lesson = (await session.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    telegram_id = (
        await session.execute(select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == student_id))
    ).scalar_one_or_none()
    return await _mark_student_attendance(
        session,
        lesson=lesson,
        student_id=student_id,
        source=AttendanceSource.BIOMETRIC,
        recipient_telegram_id=telegram_id,
    )


async def manual_correction(
    session: AsyncSession,
    teacher_id: UUID,
    lesson_id: UUID,
    student_id: UUID,
    status_value: AttendanceStatus,
    reason: str,
) -> AttendanceRecord:
    lesson_stmt = select(Lesson).where(Lesson.id == lesson_id, Lesson.teacher_id == teacher_id)
    lesson = (await session.execute(lesson_stmt)).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    if utc_now() > _as_utc(lesson.ends_at) + timedelta(days=settings.teacher_correction_window_days):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Correction window closed")

    stmt = select(AttendanceRecord).where(
        AttendanceRecord.lesson_id == lesson_id,
        AttendanceRecord.student_id == student_id,
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record:
        record.status = status_value
        record.source = AttendanceSource.TEACHER_MANUAL
        record.marked_at = utc_now()
        record.marked_by = teacher_id
        record.correction_reason = reason
    else:
        record = AttendanceRecord(
            lesson_id=lesson_id,
            student_id=student_id,
            status=status_value,
            source=AttendanceSource.TEACHER_MANUAL,
            marked_at=utc_now(),
            marked_by=teacher_id,
            correction_reason=reason,
        )
        session.add(record)
        await session.flush()

    await log_audit(
        session,
        actor_user_id=teacher_id,
        action="attendance.manual_correction",
        entity_type="attendance_record",
        entity_id=str(record.id),
        details={"lesson_id": str(lesson_id), "student_id": str(student_id), "status": status_value.value},
    )
    await session.commit()
    await session.refresh(record)
    return record


async def auto_mark_absent_for_lesson(session: AsyncSession, lesson_id: UUID) -> int:
    lesson_stmt = select(Lesson).where(Lesson.id == lesson_id)
    lesson = (await session.execute(lesson_stmt)).scalar_one_or_none()
    if not lesson:
        return 0

    _, window_end = _lesson_window(lesson)
    if utc_now() < window_end:
        return 0

    members_stmt = select(StudentGroupMembership).where(
        StudentGroupMembership.group_id == lesson.group_id,
        StudentGroupMembership.start_date <= lesson.starts_at.date(),
        or_(
            StudentGroupMembership.end_date.is_(None),
            StudentGroupMembership.end_date >= lesson.starts_at.date(),
        ),
    )
    memberships = (await session.execute(members_stmt)).scalars().all()

    created = 0
    for membership in memberships:
        exists_stmt = select(AttendanceRecord.id).where(
            AttendanceRecord.lesson_id == lesson.id,
            AttendanceRecord.student_id == membership.student_id,
        )
        exists = (await session.execute(exists_stmt)).scalar_one_or_none()
        if exists:
            continue

        telegram_id = (
            await session.execute(
                select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == membership.student_id)
            )
        ).scalar_one_or_none()

        record = AttendanceRecord(
            lesson_id=lesson.id,
            student_id=membership.student_id,
            status=AttendanceStatus.ABSENT,
            source=AttendanceSource.AUTO_ABSENCE,
            marked_at=window_end,
        )
        session.add(record)
        created += 1

        await enqueue_notification(
            session,
            event_type="absence_reason_requested",
            recipient_user_id=membership.student_id,
            recipient_telegram_id=telegram_id,
            payload={"lesson_id": str(lesson.id)},
            idempotency_key=f"absence_reason_requested:{lesson.id}:{membership.student_id}",
        )

    await session.commit()
    return created


async def create_absence_reason(
    session: AsyncSession,
    student_id: UUID,
    lesson_id: UUID,
    reason_type,
    comment: str | None,
    is_predeclared: bool,
) -> AbsenceReason:
    reason = AbsenceReason(
        lesson_id=lesson_id,
        student_id=student_id,
        reason_type=reason_type,
        comment=comment,
        is_predeclared=is_predeclared,
        moderation_status=ModerationStatus.PENDING,
    )
    session.add(reason)
    await session.commit()
    await session.refresh(reason)
    return reason


async def moderate_absence_reason(
    session: AsyncSession,
    teacher_id: UUID,
    reason_id: UUID,
    status_value: ModerationStatus,
    comment: str | None,
) -> AbsenceReason:
    stmt = (
        select(AbsenceReason)
        .join(Lesson, Lesson.id == AbsenceReason.lesson_id)
        .where(AbsenceReason.id == reason_id, Lesson.teacher_id == teacher_id)
    )
    reason = (await session.execute(stmt)).scalar_one_or_none()
    if not reason:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reason not found")

    reason.moderation_status = status_value
    reason.moderated_by = teacher_id
    reason.moderation_comment = comment
    reason.moderated_at = utc_now()

    attendance_stmt = select(AttendanceRecord).where(
        AttendanceRecord.lesson_id == reason.lesson_id,
        AttendanceRecord.student_id == reason.student_id,
    )
    attendance = (await session.execute(attendance_stmt)).scalar_one_or_none()
    if attendance:
        if status_value == ModerationStatus.ACCEPTED:
            attendance.is_excused = True
            attendance.excused_category = reason.reason_type.value
        elif status_value == ModerationStatus.REJECTED:
            attendance.is_excused = False
            attendance.excused_category = None

    telegram_id = (
        await session.execute(select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == reason.student_id))
    ).scalar_one_or_none()
    await enqueue_notification(
        session,
        event_type="reason_moderation_result",
        recipient_user_id=reason.student_id,
        recipient_telegram_id=telegram_id,
        payload={
            "lesson_id": str(reason.lesson_id),
            "reason_id": str(reason.id),
            "status": status_value.value,
            "comment": comment,
        },
        idempotency_key=f"reason_moderation_result:{reason.id}:{status_value.value}",
    )

    await log_audit(
        session,
        actor_user_id=teacher_id,
        action="absence.moderation",
        entity_type="absence_reason",
        entity_id=str(reason_id),
        details={"status": status_value.value},
    )
    await session.commit()
    await session.refresh(reason)
    return reason
