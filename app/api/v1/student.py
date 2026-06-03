from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.db import get_db_session
from app.db.enums import AbsenceReasonType, RoleCode
from app.db.models import (
    AbsenceAttachment,
    AbsenceReason,
    AttendanceRecord,
    Discipline,
    EscalationEvent,
    Group,
    Lesson,
    RatingSnapshot,
    StudentGroupMembership,
    User,
)
from app.schemas.attendance import StudentQRMarkRequest
from app.services.attendance import (
    create_absence_reason,
    mark_attendance_by_button,
    mark_attendance_by_student_qr,
)
from app.services.faq_ai import list_faq_item_rows_async
from app.services.reports import attendance_summary
from app.services.storage import save_attachment
from app.services.system_settings import ATTENDANCE_BUTTON_ENABLED_KEY, get_setting_value

router = APIRouter()


def _lesson_window_payload(lesson: Lesson) -> dict:
    starts_at = lesson.starts_at
    window_start = starts_at + timedelta(minutes=lesson.window_start_offset_minutes)
    late_after = starts_at + timedelta(minutes=lesson.late_threshold_minutes)
    return {
        "attendance_window_opens_at": window_start,
        "attendance_window_closes_at": window_start + timedelta(minutes=lesson.window_duration_minutes),
        "late_after": late_after,
    }


@router.get("/profile")
async def profile(current_user: User = Depends(require_roles(RoleCode.STUDENT))):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone_number": current_user.phone_number,
    }


@router.get("/schedule")
async def my_schedule(
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    membership_stmt = select(StudentGroupMembership.group_id).where(
        StudentGroupMembership.student_id == current_user.id,
        StudentGroupMembership.end_date.is_(None),
    )
    group_ids = [row[0] for row in (await session.execute(membership_stmt)).all()]
    if not group_ids:
        return []

    stmt = (
        select(Lesson, Group, Discipline, User)
        .join(Group, Group.id == Lesson.group_id)
        .join(Discipline, Discipline.id == Lesson.discipline_id)
        .join(User, User.id == Lesson.teacher_id)
        .where(Lesson.group_id.in_(group_ids))
    )
    if date_from:
        stmt = stmt.where(Lesson.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Lesson.starts_at <= date_to)

    lessons = (await session.execute(stmt.order_by(Lesson.starts_at.asc()))).all()
    return [
        {
            "id": lesson.id,
            "group_id": lesson.group_id,
            "group_code": group.code,
            "group_name": group.name,
            "discipline_id": lesson.discipline_id,
            "discipline_code": discipline.code,
            "discipline_name": discipline.name,
            "teacher_id": lesson.teacher_id,
            "teacher_name": teacher.full_name,
            "starts_at": lesson.starts_at,
            "ends_at": lesson.ends_at,
            "status": lesson.status.value,
            "room": lesson.room,
            **_lesson_window_payload(lesson),
        }
        for lesson, group, discipline, teacher in lessons
    ]


@router.get("/attendance/history")
async def attendance_history(
    date_from: date,
    date_to: date,
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(AttendanceRecord, Lesson, Group, Discipline, User)
        .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
        .join(Group, Group.id == Lesson.group_id)
        .join(Discipline, Discipline.id == Lesson.discipline_id)
        .join(User, User.id == Lesson.teacher_id)
        .where(
            AttendanceRecord.student_id == current_user.id,
            and_(Lesson.starts_at >= date_from, Lesson.starts_at <= date_to),
        )
        .order_by(Lesson.starts_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "lesson_id": lesson.id,
            "starts_at": lesson.starts_at,
            "discipline_id": lesson.discipline_id,
            "discipline_code": discipline.code,
            "discipline_name": discipline.name,
            "group_id": lesson.group_id,
            "group_code": group.code,
            "group_name": group.name,
            "teacher_id": lesson.teacher_id,
            "teacher_name": teacher.full_name,
            "room": lesson.room,
            "status": record.status.value,
            "source": record.source.value,
            "is_excused": record.is_excused,
            "correction_reason": record.correction_reason,
        }
        for record, lesson, group, discipline, teacher in rows
    ]


@router.get("/attendance/summary")
async def my_attendance_summary(
    date_from: date,
    date_to: date,
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    return await attendance_summary(session, date_from=date_from, date_to=date_to, student_id=current_user.id)


@router.post("/absence-reasons")
async def submit_absence_reason(
    lesson_id: UUID = Form(...),
    reason_type: AbsenceReasonType = Form(...),
    comment: str | None = Form(default=None),
    is_predeclared: bool = Form(default=False),
    file: UploadFile | None = File(default=None),
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    reason = await create_absence_reason(
        session,
        student_id=current_user.id,
        lesson_id=lesson_id,
        reason_type=reason_type,
        comment=comment,
        is_predeclared=is_predeclared,
    )

    attachment_data = None
    if file:
        file_path, size_bytes, content_type = await save_attachment(file)
        attachment = AbsenceAttachment(
            reason_id=reason.id,
            file_name=file.filename or "attachment",
            file_path=file_path,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        session.add(attachment)
        await session.commit()
        attachment_data = {
            "file_name": attachment.file_name,
            "size_bytes": attachment.size_bytes,
            "content_type": attachment.content_type,
        }

    return {
        "reason_id": reason.id,
        "lesson_id": reason.lesson_id,
        "status": reason.moderation_status.value,
        "attachment": attachment_data,
    }


@router.get("/absence-reasons")
async def my_absence_reasons(
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(AbsenceReason, Lesson, Group, Discipline)
        .join(Lesson, Lesson.id == AbsenceReason.lesson_id)
        .join(Group, Group.id == Lesson.group_id)
        .join(Discipline, Discipline.id == Lesson.discipline_id)
        .where(AbsenceReason.student_id == current_user.id)
        .order_by(AbsenceReason.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    reason_ids = [reason.id for reason, _lesson, _group, _discipline in rows]
    attachments: dict[UUID, list[dict]] = {reason_id: [] for reason_id in reason_ids}
    if reason_ids:
        attachment_rows = (
            await session.execute(select(AbsenceAttachment).where(AbsenceAttachment.reason_id.in_(reason_ids)))
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
            "discipline_name": discipline.name,
            "reason_type": reason.reason_type.value,
            "comment": reason.comment,
            "is_predeclared": reason.is_predeclared,
            "status": reason.moderation_status.value,
            "moderation_comment": reason.moderation_comment,
            "created_at": reason.created_at,
            "attachments": attachments.get(reason.id, []),
        }
        for reason, lesson, group, discipline in rows
    ]


@router.post("/attendance/mark-qr")
async def mark_qr_attendance(
    payload: StudentQRMarkRequest,
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    record = await mark_attendance_by_student_qr(session, student_id=current_user.id, qr_token=payload.qr_token)
    return {
        "attendance_id": record.id,
        "lesson_id": record.lesson_id,
        "student_id": record.student_id,
        "status": record.status.value,
    }


@router.post("/attendance/mark-button")
async def mark_button_attendance(
    lesson_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    enabled = bool(await get_setting_value(session, ATTENDANCE_BUTTON_ENABLED_KEY, True))
    if not enabled:
        raise HTTPException(status_code=403, detail="Attendance button is disabled")
    record = await mark_attendance_by_button(session, student_id=current_user.id, lesson_id=lesson_id)
    return {
        "attendance_id": record.id,
        "lesson_id": record.lesson_id,
        "student_id": record.student_id,
        "status": record.status.value,
    }


@router.get("/rating")
async def my_rating(
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(RatingSnapshot)
        .where(RatingSnapshot.student_id == current_user.id)
        .order_by(RatingSnapshot.calculated_at.desc())
        .limit(20)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "score": float(r.score),
            "attendance_pct": float(r.attendance_pct),
            "late_count": r.late_count,
            "unexcused_absence_count": r.unexcused_absence_count,
            "period_start": r.period_start,
            "period_end": r.period_end,
        }
        for r in rows
    ]


@router.get("/warnings")
async def my_warnings(
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(EscalationEvent)
        .where(EscalationEvent.student_id == current_user.id)
        .order_by(EscalationEvent.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": e.id,
            "status": e.status.value,
            "reason": e.reason_payload,
            "created_at": e.created_at,
        }
        for e in rows
    ]


@router.get("/faq")
async def faq_search(
    query: str | None = None,
    category_id: UUID | None = None,
    current_user: User = Depends(require_roles(RoleCode.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
):
    _ = (current_user, session)
    return [
        {
            "id": row["id"],
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "question": row["question"],
            "answer": row["answer"],
            "keywords": row["keywords"],
        }
        for row in await list_faq_item_rows_async(query, category_id=category_id)
    ]
