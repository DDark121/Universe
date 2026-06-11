from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.security import decode_token
from app.core.time import utc_now
from app.db.enums import BroadcastScope, DeliveryStatus, RoleCode
from app.db.models import (
    AbsenceAttachment,
    AbsenceReason,
    AttendanceRecord,
    Broadcast,
    BroadcastRecipient,
    Discipline,
    Group,
    Lesson,
    QRSession,
    StudentGroupMembership,
    TeacherAssignment,
    TelegramAccount,
    User,
)
from app.schemas.attendance import (
    AbsenceModerationRequest,
    AttendanceManualCorrectionRequest,
    DynamicQRSessionStartRequest,
    DynamicQRSessionStartResponse,
    QRGenerateRequest,
    QRGenerateResponse,
)
from app.services.attendance import (
    build_dynamic_qr_token,
    create_dynamic_qr_session,
    generate_qr_token,
    manual_correction,
    moderate_absence_reason,
    stop_dynamic_qr_session,
)
from app.services.notifications import enqueue_notification
from app.services.reports import attendance_summary

router = APIRouter()
settings = get_settings()


async def _teacher_from_ws_token(token: str | None, session: AsyncSession) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing subject")

    user = (
        await session.execute(select(User).where(User.id == UUID(user_id)).options(selectinload(User.roles)))
    ).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")

    roles = {role.code for role in user.roles}
    if RoleCode.TEACHER not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return user


async def _teacher_lesson_or_404(
    session: AsyncSession,
    lesson_id: UUID,
    teacher_id: UUID,
) -> tuple[Lesson, Group, Discipline]:
    row = (
        await session.execute(
            select(Lesson, Group, Discipline)
            .join(Group, Group.id == Lesson.group_id)
            .join(Discipline, Discipline.id == Lesson.discipline_id)
            .where(Lesson.id == lesson_id, Lesson.teacher_id == teacher_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return row


@router.get("/lessons")
async def my_lessons(
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Lesson, Group, Discipline)
        .join(Group, Group.id == Lesson.group_id)
        .join(Discipline, Discipline.id == Lesson.discipline_id)
        .where(Lesson.teacher_id == current_user.id)
    )
    if date_from:
        stmt = stmt.where(Lesson.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Lesson.starts_at < date_to + timedelta(days=1))

    rows = (await session.execute(stmt.order_by(Lesson.starts_at.asc()))).all()
    return [
        {
            "id": lesson.id,
            "group_id": lesson.group_id,
            "group_code": group.code,
            "group_name": group.name,
            "discipline_id": lesson.discipline_id,
            "discipline_code": discipline.code,
            "discipline_name": discipline.name,
            "starts_at": lesson.starts_at,
            "ends_at": lesson.ends_at,
            "status": lesson.status.value,
            "room": lesson.room,
        }
        for lesson, group, discipline in rows
    ]


@router.get("/groups")
async def teacher_groups(
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    assignment_rows = (
        await session.execute(
            select(TeacherAssignment.group_id).where(
                TeacherAssignment.teacher_id == current_user.id,
                TeacherAssignment.is_active.is_(True),
            )
        )
    ).all()
    lesson_rows = (
        await session.execute(select(Lesson.group_id).where(Lesson.teacher_id == current_user.id))
    ).all()
    group_ids = {group_id for (group_id,) in assignment_rows + lesson_rows}
    if not group_ids:
        return []

    rows = (
        await session.execute(select(Group).where(Group.id.in_(group_ids)).order_by(Group.code.asc()))
    ).scalars().all()
    return [{"id": row.id, "code": row.code, "name": row.name} for row in rows]


@router.post("/qr/generate", response_model=QRGenerateResponse)
async def generate_qr(
    payload: QRGenerateRequest,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> QRGenerateResponse:
    token, token_row = await generate_qr_token(session, lesson_id=payload.lesson_id, teacher_id=current_user.id)
    return QRGenerateResponse(
        token=token,
        deeplink=f"t.me/{settings.tg_bot_username}?start=qr_{token}",
        expires_at=token_row.expires_at,
    )


@router.post("/qr/sessions/start", response_model=DynamicQRSessionStartResponse)
async def start_dynamic_qr_session(
    payload: DynamicQRSessionStartRequest,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> DynamicQRSessionStartResponse:
    qr_session = await create_dynamic_qr_session(
        session,
        lesson_id=payload.lesson_id,
        teacher_id=current_user.id,
    )
    return DynamicQRSessionStartResponse(
        session_id=qr_session.id,
        ws_url=f"/api/v1/teacher/qr/sessions/{qr_session.id}/stream",
        session_expires_at=qr_session.expires_at,
    )


@router.post("/qr/sessions/{session_id}/stop")
async def stop_qr_session(
    session_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    qr_session = await stop_dynamic_qr_session(session, session_id=session_id, teacher_id=current_user.id)
    return {
        "session_id": qr_session.id,
        "is_active": qr_session.is_active,
        "stopped_at": qr_session.stopped_at,
    }


@router.websocket("/qr/sessions/{session_id}/stream")
async def stream_dynamic_qr_tokens(
    websocket: WebSocket,
    session_id: UUID,
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    await websocket.accept()

    try:
        current_user = await _teacher_from_ws_token(token, session)
        qr_session = (
            await session.execute(
                select(QRSession).where(
                    QRSession.id == session_id,
                    QRSession.teacher_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if not qr_session:
            await websocket.send_json({"error": "QR session not found"})
            await websocket.close(code=4404)
            return

        while True:
            qr_session = (
                await session.execute(select(QRSession).where(QRSession.id == session_id))
            ).scalar_one_or_none()
            if not qr_session or (not qr_session.is_active) or utc_now() > qr_session.expires_at:
                await websocket.send_json({"event": "session_closed", "session_id": str(session_id)})
                await websocket.close(code=1000)
                return

            token_value, slot_index = build_dynamic_qr_token(qr_session)
            qr_session.last_slot_index = slot_index
            await session.commit()
            await websocket.send_json(
                {
                    "event": "qr_slot",
                    "session_id": str(qr_session.id),
                    "lesson_id": str(qr_session.lesson_id),
                    "slot_index": slot_index,
                    "qr_token": token_value,
                    "deeplink": f"t.me/{settings.tg_bot_username}?start=qr_{token_value}",
                    "expires_at": qr_session.expires_at.isoformat(),
                }
            )
            await asyncio.sleep(max(1, settings.qr_dynamic_slot_seconds))
    except (HTTPException, WebSocketDisconnect) as exc:
        if isinstance(exc, HTTPException):
            await websocket.send_json({"error": exc.detail})
            await websocket.close(code=4403)
    except Exception:
        await websocket.close(code=1011)


@router.get("/lessons/{lesson_id}/attendance")
async def lesson_attendance(
    lesson_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    lesson, group, discipline = await _teacher_lesson_or_404(session, lesson_id=lesson_id, teacher_id=current_user.id)

    rows = (
        await session.execute(
            select(User, StudentGroupMembership, AttendanceRecord)
            .join(StudentGroupMembership, StudentGroupMembership.student_id == User.id)
            .outerjoin(
                AttendanceRecord,
                and_(
                    AttendanceRecord.lesson_id == lesson.id,
                    AttendanceRecord.student_id == User.id,
                ),
            )
            .where(
                StudentGroupMembership.group_id == lesson.group_id,
                StudentGroupMembership.start_date <= lesson.starts_at.date(),
                or_(
                    StudentGroupMembership.end_date.is_(None),
                    StudentGroupMembership.end_date >= lesson.starts_at.date(),
                ),
            )
            .order_by(User.full_name.asc(), User.username.asc())
        )
    ).all()

    return {
        "lesson": {
            "id": lesson.id,
            "group_id": lesson.group_id,
            "group_code": group.code,
            "group_name": group.name,
            "discipline_id": lesson.discipline_id,
            "discipline_code": discipline.code,
            "discipline_name": discipline.name,
            "starts_at": lesson.starts_at,
            "ends_at": lesson.ends_at,
            "status": lesson.status.value,
            "room": lesson.room,
        },
        "students": [
            {
                "student_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "attendance_id": record.id if record else None,
                "status": record.status.value if record else None,
                "source": record.source.value if record else None,
                "marked_at": record.marked_at if record else None,
                "is_excused": record.is_excused if record else False,
                "correction_reason": record.correction_reason if record else None,
            }
            for user, _membership, record in rows
        ],
    }


@router.post("/attendance/correct")
async def correct_attendance(
    payload: AttendanceManualCorrectionRequest,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    record = await manual_correction(
        session,
        teacher_id=current_user.id,
        lesson_id=payload.lesson_id,
        student_id=payload.student_id,
        status_value=payload.status,
        reason=payload.reason,
    )
    return {
        "id": record.id,
        "lesson_id": record.lesson_id,
        "student_id": record.student_id,
        "status": record.status.value,
        "source": record.source.value,
    }


@router.get("/absence-reasons")
async def list_absence_reasons(
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(AbsenceReason, Lesson, Group, User)
        .join(Lesson, Lesson.id == AbsenceReason.lesson_id)
        .join(Group, Group.id == Lesson.group_id)
        .join(User, User.id == AbsenceReason.student_id)
        .where(Lesson.teacher_id == current_user.id)
        .order_by(AbsenceReason.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    reason_ids = [reason.id for reason, _lesson, _group, _student in rows]
    attachments: dict[UUID, list[dict]] = {reason_id: [] for reason_id in reason_ids}
    if reason_ids:
        attachment_rows = (
            await session.execute(
                select(AbsenceAttachment).where(AbsenceAttachment.reason_id.in_(reason_ids))
            )
        ).scalars().all()
        for attachment in attachment_rows:
            attachments.setdefault(attachment.reason_id, []).append(
                {
                    "id": attachment.id,
                    "file_name": attachment.file_name,
                    "content_type": attachment.content_type,
                    "size_bytes": attachment.size_bytes,
                    "uploaded_at": attachment.uploaded_at,
                }
            )

    return [
        {
            "id": reason.id,
            "lesson_id": reason.lesson_id,
            "lesson_starts_at": lesson.starts_at,
            "group_name": group.name,
            "student_id": reason.student_id,
            "student_name": student.full_name,
            "reason_type": reason.reason_type.value,
            "comment": reason.comment,
            "is_predeclared": reason.is_predeclared,
            "status": reason.moderation_status.value,
            "moderation_comment": reason.moderation_comment,
            "created_at": reason.created_at,
            "attachments": attachments.get(reason.id, []),
        }
        for reason, lesson, group, student in rows
    ]


@router.get("/absence-reasons/attachments/{attachment_id}")
async def download_absence_attachment(
    attachment_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (
        await session.execute(
            select(AbsenceAttachment, AbsenceReason, Lesson)
            .join(AbsenceReason, AbsenceReason.id == AbsenceAttachment.reason_id)
            .join(Lesson, Lesson.id == AbsenceReason.lesson_id)
            .where(
                AbsenceAttachment.id == attachment_id,
                Lesson.teacher_id == current_user.id,
            )
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    attachment, _reason, _lesson = row
    path = Path(attachment.file_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file not found")

    return FileResponse(
        path=path,
        filename=attachment.file_name,
        media_type=attachment.content_type,
    )


@router.post("/absence-reasons/moderate")
async def moderate_reason(
    payload: AbsenceModerationRequest,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    reason = await moderate_absence_reason(
        session,
        teacher_id=current_user.id,
        reason_id=payload.reason_id,
        status_value=payload.status,
        comment=payload.comment,
    )
    return {
        "id": reason.id,
        "status": reason.moderation_status.value,
        "student_id": reason.student_id,
    }


@router.get("/reports/attendance")
async def teacher_attendance_report(
    date_from: date,
    date_to: date,
    group_id: UUID | None = None,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    return await attendance_summary(
        session,
        date_from=date_from,
        date_to=date_to,
        group_id=group_id,
        teacher_id=current_user.id,
    )


@router.post("/broadcasts")
async def teacher_broadcast(
    group_id: UUID,
    message: str,
    current_user: User = Depends(require_roles(RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
):
    assignment = (
        await session.execute(
            select(Lesson.id).where(Lesson.teacher_id == current_user.id, Lesson.group_id == group_id).limit(1)
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=403, detail="No access to this group")

    broadcast = Broadcast(
        sender_id=current_user.id,
        scope=BroadcastScope.GROUP,
        group_id=group_id,
        message=message,
    )
    session.add(broadcast)
    await session.flush()

    members = (
        await session.execute(
            select(StudentGroupMembership.student_id)
            .where(StudentGroupMembership.group_id == group_id, StudentGroupMembership.end_date.is_(None))
        )
    ).all()
    for (student_id,) in members:
        telegram = (
            await session.execute(select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == student_id))
        ).scalar_one_or_none()

        session.add(
            BroadcastRecipient(
                broadcast_id=broadcast.id,
                user_id=student_id,
                telegram_id=telegram,
                status=DeliveryStatus.PENDING,
            )
        )

        await enqueue_notification(
            session,
            event_type="teacher_broadcast",
            recipient_user_id=student_id,
            recipient_telegram_id=telegram,
            payload={"message": message, "group_id": str(group_id)},
            idempotency_key=f"teacher_broadcast:{broadcast.id}:{student_id}",
        )

    await session.commit()
    return {"broadcast_id": broadcast.id, "recipients": len(members)}
