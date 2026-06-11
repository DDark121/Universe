from __future__ import annotations

import hashlib
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import tg_rate_limit, verify_service_token
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.logging import get_logger
from app.core.security import generate_temp_password, hash_password
from app.core.time import utc_now
from app.db.enums import BindingRequestStatus, RoleCode
from app.db.models import (
    AbsenceAttachment,
    AbsenceReason,
    AttendanceRecord,
    Discipline,
    EscalationEvent,
    Group,
    GroupTelegramChat,
    InviteActivation,
    InviteCode,
    Lesson,
    LessonActivityScore,
    RatingSnapshot,
    Role,
    StudentGroupMembership,
    TelegramAccount,
    TelegramBindingRequest,
    User,
)
from app.schemas.attendance import AbsenceReasonCreateRequest, AttendanceMarkRequest
from app.schemas.common import ApiMessage
from app.schemas.tg import (
    BindingRequestCreate,
    InviteBindRequest,
    TelegramAssistantReplyRequest,
    TelegramAssistantReplyResponse,
    TelegramAuthExchangeRequest,
    TelegramAuthExchangeResponse,
    TelegramBootstrapResponse,
    TelegramButtonAttendanceRequest,
    TelegramContextResponse,
    TelegramLessonActivityScoreRequest,
    TelegramLinkedUserResponse,
    TelegramStudentFaqItemResponse,
    TelegramTeacherBroadcastRequest,
    TelegramTeacherModerationRequest,
    TelegramTeacherQrGenerateRequest,
)
from app.services.activity import upsert_lesson_activity_score
from app.services.attendance import (
    create_absence_reason,
    generate_qr_token,
    mark_attendance_by_button,
    mark_attendance_by_qr,
    moderate_absence_reason,
)
from app.services.auth import issue_token_pair
from app.services.faq_ai import generate_assistant_reply, list_faq_item_rows_async
from app.services.notifications import enqueue_notification
from app.services.reports import attendance_summary
from app.services.system_settings import ATTENDANCE_BUTTON_ENABLED_KEY, get_setting_value

router = APIRouter(dependencies=[Depends(verify_service_token), Depends(tg_rate_limit)])
settings = get_settings()
logger = get_logger(__name__)


def _linked_user_payload(user: User) -> TelegramLinkedUserResponse:
    return TelegramLinkedUserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        phone_number=user.phone_number,
        roles=[role.code.value for role in user.roles],
        is_active=user.is_active,
        must_change_password=user.must_change_password,
    )


def _lesson_window_payload(lesson: Lesson) -> dict:
    starts_at = lesson.starts_at
    window_start = starts_at + timedelta(minutes=lesson.window_start_offset_minutes)
    return {
        "attendance_window_opens_at": window_start,
        "attendance_window_closes_at": window_start + timedelta(minutes=lesson.window_duration_minutes),
        "late_after": starts_at + timedelta(minutes=lesson.late_threshold_minutes),
    }


async def _linked_user_or_error(
    session: AsyncSession,
    telegram_id: int,
    *roles: RoleCode,
) -> tuple[TelegramAccount, User]:
    account = (
        await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account is not linked")

    user = (
        await session.execute(select(User).where(User.id == account.user_id).options(selectinload(User.roles)))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    if roles:
        user_roles = {role.code for role in user.roles}
        if not any(role in user_roles for role in roles):
            raise HTTPException(status_code=403, detail="Linked user has insufficient permissions")

    return account, user


async def _student_group_ids(session: AsyncSession, student_id: UUID) -> list[UUID]:
    rows = (
        await session.execute(
            select(StudentGroupMembership.group_id).where(
                StudentGroupMembership.student_id == student_id,
                or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= date.today()),
            )
        )
    ).all()
    return [group_id for (group_id,) in rows]


async def _teacher_lesson_row(session: AsyncSession, lesson_id: UUID, teacher_id: UUID):
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


async def _faq_payload(*, query: str | None = None, category_id: UUID | None = None):
    return [
        TelegramStudentFaqItemResponse(
            id=row["id"],
            category_id=row["category_id"],
            category_name=row["category_name"],
            question=row["question"],
            answer=row["answer"],
            keywords=row["keywords"],
        )
        for row in await list_faq_item_rows_async(query, category_id=category_id)
    ]


@router.post("/bind/invite", response_model=ApiMessage)
async def bind_with_invite(
    payload: InviteBindRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    invite = (
        await session.execute(select(InviteCode).where(InviteCode.code == payload.invite_code, InviteCode.is_active.is_(True)))
    ).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite code not found")
    if invite.expires_at < utc_now():
        raise HTTPException(status_code=400, detail="Invite code expired")
    if invite.activation_count >= invite.max_activations:
        raise HTTPException(status_code=400, detail="Invite activation limit reached")

    existing_link = (
        await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == payload.telegram_id))
    ).scalar_one_or_none()
    if existing_link:
        raise HTTPException(status_code=409, detail="Telegram ID already linked")

    role = (await session.execute(select(Role).where(Role.code == invite.role_code))).scalar_one_or_none()

    user = None
    if payload.username:
        user = (await session.execute(select(User).where(User.username == payload.username))).scalar_one_or_none()
    if not user:
        user = User(
            username=f"tg_{payload.telegram_id}",
            full_name=f"{payload.first_name or ''} {payload.last_name or ''}".strip() or f"tg_{payload.telegram_id}",
            password_hash=hash_password(generate_temp_password()),
            must_change_password=True,
            is_active=True,
            roles=[role] if role else [],
        )
        session.add(user)
        await session.flush()

    session.add(
        TelegramAccount(
            user_id=user.id,
            telegram_id=payload.telegram_id,
            username=payload.username,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
    )
    if invite.role_code == RoleCode.STUDENT and invite.group_id:
        membership = (
            await session.execute(
                select(StudentGroupMembership).where(
                    StudentGroupMembership.student_id == user.id,
                    StudentGroupMembership.group_id == invite.group_id,
                    StudentGroupMembership.end_date.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not membership:
            session.add(
                StudentGroupMembership(
                    student_id=user.id,
                    group_id=invite.group_id,
                    start_date=utc_now().date(),
                    is_primary=True,
                )
            )

    invite.activation_count += 1
    if invite.activation_count >= invite.max_activations:
        invite.is_active = False
    session.add(InviteActivation(invite_code_id=invite.id, user_id=user.id, telegram_id=payload.telegram_id))
    await session.commit()
    return ApiMessage(message="Telegram account linked")


@router.post("/binding-requests", response_model=ApiMessage)
async def create_binding_request(
    payload: BindingRequestCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    logger.info(
        "tg_binding_request_create",
        telegram_id=payload.telegram_id,
        has_group_code=bool(payload.group_code),
        has_note=bool(payload.note),
    )
    existing_link = (
        await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == payload.telegram_id))
    ).scalar_one_or_none()
    if existing_link:
        raise HTTPException(status_code=409, detail="Telegram ID already linked")

    existing_pending = (
        await session.execute(
            select(TelegramBindingRequest).where(
                TelegramBindingRequest.telegram_id == payload.telegram_id,
                TelegramBindingRequest.status == BindingRequestStatus.PENDING,
            )
        )
    ).scalar_one_or_none()
    if existing_pending:
        return ApiMessage(message="Request already pending")

    session.add(
        TelegramBindingRequest(
            telegram_id=payload.telegram_id,
            telegram_username=payload.telegram_username,
            full_name=payload.full_name,
            group_code=payload.group_code,
            note=payload.note,
            requested_user_id=payload.requested_user_id,
            status=BindingRequestStatus.PENDING,
        )
    )
    await session.commit()
    return ApiMessage(message="Binding request submitted")


@router.get("/binding-requests/{telegram_id}")
async def get_binding_request_status(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    req = (
        await session.execute(
            select(TelegramBindingRequest)
            .where(TelegramBindingRequest.telegram_id == telegram_id)
            .order_by(TelegramBindingRequest.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not req:
        return {"status": "not_found"}
    return {
        "status": req.status.value,
        "resolved_at": req.resolved_at,
        "requested_user_id": req.requested_user_id,
        "full_name": req.full_name,
        "telegram_username": req.telegram_username,
        "group_code": req.group_code,
        "note": req.note,
    }


@router.get("/bootstrap/{telegram_id}", response_model=TelegramBootstrapResponse)
async def tg_bootstrap(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> TelegramBootstrapResponse:
    account = (
        await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if account:
        user = (
            await session.execute(select(User).where(User.id == account.user_id).options(selectinload(User.roles)))
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return TelegramBootstrapResponse(status="linked", user=_linked_user_payload(user))

    request = (
        await session.execute(
            select(TelegramBindingRequest)
            .where(TelegramBindingRequest.telegram_id == telegram_id)
            .order_by(TelegramBindingRequest.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not request:
        return TelegramBootstrapResponse(status="link_required")

    status_value = (
        request.status.value
        if request.status in {BindingRequestStatus.PENDING, BindingRequestStatus.REJECTED}
        else "link_required"
    )
    return TelegramBootstrapResponse(
        status=status_value,
        requested_user_id=request.requested_user_id,
        requested_full_name=request.full_name,
        telegram_username=request.telegram_username,
        group_code=request.group_code,
        note=request.note,
        resolved_at=request.resolved_at,
    )


@router.get("/context/{telegram_id}", response_model=TelegramContextResponse)
async def tg_context(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> TelegramContextResponse:
    _account, user = await _linked_user_or_error(session, telegram_id)
    return TelegramContextResponse(user_id=user.id, full_name=user.full_name, roles=[r.code.value for r in user.roles])


@router.post("/auth/exchange", response_model=TelegramAuthExchangeResponse)
async def exchange_tg_auth(
    payload: TelegramAuthExchangeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TelegramAuthExchangeResponse:
    _account, user = await _linked_user_or_error(session, payload.telegram_id)
    tokens = await issue_token_pair(
        session,
        user,
        ip_address=None,
        user_agent="tg-service",
        audit_action="auth.telegram_exchange",
    )
    return TelegramAuthExchangeResponse(**tokens.model_dump(), user=_linked_user_payload(user))


@router.post("/attendance/mark")
async def mark_attendance(
    payload: AttendanceMarkRequest,
    session: AsyncSession = Depends(get_db_session),
):
    logger.info("tg_mark_attendance_request", telegram_id=payload.telegram_id)
    record = await mark_attendance_by_qr(session, telegram_id=payload.telegram_id, qr_token=payload.qr_token)
    logger.info(
        "tg_mark_attendance_success",
        telegram_id=payload.telegram_id,
        lesson_id=str(record.lesson_id),
        student_id=str(record.student_id),
        status=record.status.value,
    )
    return {
        "attendance_id": record.id,
        "lesson_id": record.lesson_id,
        "student_id": record.student_id,
        "status": record.status.value,
    }


@router.post("/student/attendance/button")
async def mark_student_attendance_button(
    payload: TelegramButtonAttendanceRequest,
    session: AsyncSession = Depends(get_db_session),
):
    enabled = bool(await get_setting_value(session, ATTENDANCE_BUTTON_ENABLED_KEY, True))
    if not enabled:
        raise HTTPException(status_code=403, detail="Attendance button is disabled")
    account, user = await _linked_user_or_error(session, payload.telegram_id, RoleCode.STUDENT)
    record = await mark_attendance_by_button(
        session,
        student_id=user.id,
        lesson_id=payload.lesson_id,
        recipient_telegram_id=account.telegram_id,
    )
    return {
        "attendance_id": record.id,
        "lesson_id": record.lesson_id,
        "student_id": record.student_id,
        "status": record.status.value,
    }


@router.get("/student/schedule/{telegram_id}")
async def student_schedule(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
    date_from: date | None = None,
    date_to: date | None = None,
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.STUDENT)
    group_ids = await _student_group_ids(session, user.id)
    if not group_ids:
        return []
    stmt = (
        select(Lesson, Group, Discipline, User)
        .join(Group, Group.id == Lesson.group_id)
        .join(Discipline, Discipline.id == Lesson.discipline_id)
        .join(User, User.id == Lesson.teacher_id)
        .where(Lesson.group_id.in_(group_ids))
        .order_by(Lesson.starts_at.asc())
    )
    if date_from:
        stmt = stmt.where(Lesson.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Lesson.starts_at < date_to + timedelta(days=1))
    rows = (await session.execute(stmt)).all()
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
        for lesson, group, discipline, teacher in rows
    ]


@router.get("/student/attendance-summary/{telegram_id}")
async def student_attendance_summary(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
    date_from: date | None = None,
    date_to: date | None = None,
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.STUDENT)
    period_end = date_to or utc_now().date()
    period_start = date_from or (period_end - timedelta(days=30))
    return await attendance_summary(session, date_from=period_start, date_to=period_end, student_id=user.id)


@router.get("/student/rating/{telegram_id}")
async def student_rating(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.STUDENT)
    rows = (
        await session.execute(
            select(RatingSnapshot)
            .where(RatingSnapshot.student_id == user.id)
            .order_by(RatingSnapshot.calculated_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return [
        {
            "score": float(row.score),
            "attendance_pct": float(row.attendance_pct),
            "late_count": row.late_count,
            "unexcused_absence_count": row.unexcused_absence_count,
            "period_start": row.period_start,
            "period_end": row.period_end,
        }
        for row in rows
    ]


@router.get("/student/warnings/{telegram_id}")
async def student_warnings(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.STUDENT)
    rows = (
        await session.execute(
            select(EscalationEvent)
            .where(EscalationEvent.student_id == user.id)
            .order_by(EscalationEvent.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "status": row.status.value,
            "reason": row.reason_payload,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/student/faq/{telegram_id}", response_model=list[TelegramStudentFaqItemResponse])
async def student_faq(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
    query: str | None = None,
    category_id: UUID | None = None,
):
    await _linked_user_or_error(session, telegram_id, RoleCode.STUDENT)
    return await _faq_payload(query=query, category_id=category_id)


@router.post("/student/absence-reasons/{telegram_id}")
async def submit_student_absence_reason(
    telegram_id: int,
    payload: AbsenceReasonCreateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.STUDENT)
    reason = await create_absence_reason(
        session,
        student_id=user.id,
        lesson_id=payload.lesson_id,
        reason_type=payload.reason_type,
        comment=payload.comment,
        is_predeclared=payload.is_predeclared,
    )
    return {"reason_id": reason.id, "status": reason.moderation_status.value}


@router.get("/teacher/lessons/{telegram_id}")
async def teacher_lessons(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
    date_from: date | None = None,
    date_to: date | None = None,
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.TEACHER)
    stmt = (
        select(Lesson, Group, Discipline)
        .join(Group, Group.id == Lesson.group_id)
        .join(Discipline, Discipline.id == Lesson.discipline_id)
        .where(Lesson.teacher_id == user.id)
        .order_by(Lesson.starts_at.asc())
    )
    if date_from:
        stmt = stmt.where(Lesson.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Lesson.starts_at < date_to + timedelta(days=1))
    rows = (await session.execute(stmt)).all()
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


@router.get("/teacher/lessons/{telegram_id}/{lesson_id}/attendance")
async def teacher_lesson_attendance(
    telegram_id: int,
    lesson_id: UUID,
    session: AsyncSession = Depends(get_db_session),
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.TEACHER)
    lesson, group, discipline = await _teacher_lesson_row(session, lesson_id, user.id)
    rows = (
        await session.execute(
            select(User, StudentGroupMembership, AttendanceRecord, LessonActivityScore)
            .join(StudentGroupMembership, StudentGroupMembership.student_id == User.id)
            .outerjoin(
                AttendanceRecord,
                and_(
                    AttendanceRecord.lesson_id == lesson.id,
                    AttendanceRecord.student_id == User.id,
                ),
            )
            .outerjoin(
                LessonActivityScore,
                and_(
                    LessonActivityScore.lesson_id == lesson.id,
                    LessonActivityScore.student_id == User.id,
                ),
            )
            .where(
                StudentGroupMembership.group_id == lesson.group_id,
                or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= lesson.starts_at.date()),
            )
            .order_by(User.full_name.asc())
        )
    ).all()
    return {
        "lesson": {
            "id": lesson.id,
            "group_name": group.name,
            "discipline_name": discipline.name,
            "starts_at": lesson.starts_at,
            "status": lesson.status.value,
        },
        "students": [
            {
                "student_id": student.id,
                "full_name": student.full_name,
                "status": record.status.value if record else None,
                "source": record.source.value if record else None,
                "marked_at": record.marked_at if record else None,
                "is_excused": record.is_excused if record else False,
                "correction_reason": record.correction_reason if record else None,
                "activity_score": float(activity.score) if activity else None,
                "activity_comment": activity.comment if activity else None,
            }
            for student, _membership, record, activity in rows
        ],
    }


@router.post("/teacher/qr/generate")
async def teacher_generate_qr(
    payload: TelegramTeacherQrGenerateRequest,
    session: AsyncSession = Depends(get_db_session),
):
    logger.info(
        "tg_teacher_qr_generate_request",
        telegram_id=payload.telegram_id,
        lesson_id=str(payload.lesson_id),
    )
    _account, user = await _linked_user_or_error(session, payload.telegram_id, RoleCode.TEACHER)
    token, token_row = await generate_qr_token(session, lesson_id=payload.lesson_id, teacher_id=user.id)
    logger.info(
        "tg_teacher_qr_generate_success",
        telegram_id=payload.telegram_id,
        lesson_id=str(payload.lesson_id),
        expires_at=token_row.expires_at,
    )
    return {
        "token": token,
        "deeplink": f"t.me/{settings.tg_bot_username}?start=qr_{token}",
        "expires_at": token_row.expires_at,
    }


@router.get("/teacher/absence-reasons/{telegram_id}")
async def teacher_absence_reasons(
    telegram_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    _account, user = await _linked_user_or_error(session, telegram_id, RoleCode.TEACHER)
    rows = (
        await session.execute(
            select(AbsenceReason, Lesson, User, Group, Discipline)
            .join(Lesson, Lesson.id == AbsenceReason.lesson_id)
            .join(User, User.id == AbsenceReason.student_id)
            .join(Group, Group.id == Lesson.group_id)
            .join(Discipline, Discipline.id == Lesson.discipline_id)
            .where(Lesson.teacher_id == user.id)
            .order_by(AbsenceReason.created_at.desc())
        )
    ).all()
    reason_ids = [reason.id for reason, _lesson, _student, _group, _discipline in rows]
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
                }
            )
    return [
        {
            "id": reason.id,
            "lesson_id": lesson.id,
            "lesson_starts_at": lesson.starts_at,
            "discipline_name": discipline.name,
            "group_name": group.name,
            "student_name": student.full_name,
            "reason_type": reason.reason_type.value,
            "comment": reason.comment,
            "is_predeclared": reason.is_predeclared,
            "status": reason.moderation_status.value,
            "moderation_comment": reason.moderation_comment,
            "attachments": attachments.get(reason.id, []),
        }
        for reason, lesson, student, group, discipline in rows
    ]


@router.post("/teacher/absence-reasons/moderate")
async def teacher_moderate_reason(
    payload: TelegramTeacherModerationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    logger.info(
        "tg_teacher_reason_moderation_request",
        telegram_id=payload.telegram_id,
        reason_id=str(payload.reason_id),
        status=payload.status,
    )
    _account, user = await _linked_user_or_error(session, payload.telegram_id, RoleCode.TEACHER)
    reason = await moderate_absence_reason(
        session,
        teacher_id=user.id,
        reason_id=payload.reason_id,
        status_value=payload.status,
        comment=payload.comment,
    )
    logger.info(
        "tg_teacher_reason_moderation_success",
        telegram_id=payload.telegram_id,
        reason_id=str(payload.reason_id),
        status=reason.moderation_status.value,
    )
    return {"reason_id": reason.id, "status": reason.moderation_status.value}


@router.post("/teacher/broadcasts")
async def teacher_broadcast(
    payload: TelegramTeacherBroadcastRequest,
    session: AsyncSession = Depends(get_db_session),
):
    logger.info(
        "tg_teacher_broadcast_request",
        telegram_id=payload.telegram_id,
        group_id=str(payload.group_id),
    )
    _account, user = await _linked_user_or_error(session, payload.telegram_id, RoleCode.TEACHER)
    lesson_exists = (
        await session.execute(
            select(Lesson.id).where(Lesson.teacher_id == user.id, Lesson.group_id == payload.group_id).limit(1)
        )
    ).scalar_one_or_none()
    if not lesson_exists:
        raise HTTPException(status_code=403, detail="No access to this group")

    students = (
        await session.execute(
            select(StudentGroupMembership.student_id)
            .where(StudentGroupMembership.group_id == payload.group_id, StudentGroupMembership.end_date.is_(None))
        )
    ).all()
    for student_id, in students:
        student_telegram_id = (
            await session.execute(select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == student_id))
        ).scalar_one_or_none()
        await enqueue_notification(
            session,
            event_type="teacher_broadcast",
            recipient_user_id=student_id,
            recipient_telegram_id=student_telegram_id,
            payload={"message": payload.message, "group_id": str(payload.group_id)},
            idempotency_key=(
                f"tg_teacher_broadcast:{payload.group_id}:{student_id}:"
                f"{hashlib.sha256(payload.message.encode('utf-8')).hexdigest()[:16]}"
            ),
        )

    group_chat = (
        await session.execute(
            select(GroupTelegramChat).where(
                GroupTelegramChat.group_id == payload.group_id,
                GroupTelegramChat.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if group_chat:
        await enqueue_notification(
            session,
            event_type="teacher_broadcast",
            recipient_user_id=None,
            recipient_telegram_id=group_chat.telegram_chat_id,
            payload={"message": payload.message, "group_id": str(payload.group_id), "delivery": "group_chat"},
            idempotency_key=(
                f"tg_teacher_group_chat_broadcast:{payload.group_id}:{group_chat.telegram_chat_id}:"
                f"{hashlib.sha256(payload.message.encode('utf-8')).hexdigest()[:16]}"
            ),
        )
    await session.commit()
    logger.info(
        "tg_teacher_broadcast_queued",
        telegram_id=payload.telegram_id,
        group_id=str(payload.group_id),
        recipients=len(students),
        group_chat_enabled=bool(group_chat),
    )
    return {"recipients": len(students)}


@router.post("/teacher/activity")
async def teacher_activity_score(
    payload: TelegramLessonActivityScoreRequest,
    session: AsyncSession = Depends(get_db_session),
):
    _account, user = await _linked_user_or_error(session, payload.telegram_id, RoleCode.TEACHER)
    score = await upsert_lesson_activity_score(
        session,
        teacher_id=user.id,
        lesson_id=payload.lesson_id,
        student_id=payload.student_id,
        score=payload.score,
        comment=payload.comment,
    )
    return {
        "id": score.id,
        "lesson_id": score.lesson_id,
        "student_id": score.student_id,
        "score": float(score.score),
        "comment": score.comment,
    }


@router.post("/assistant/reply", response_model=TelegramAssistantReplyResponse)
async def assistant_reply(
    payload: TelegramAssistantReplyRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TelegramAssistantReplyResponse:
    logger.info("tg_assistant_request", telegram_id=payload.telegram_id)
    reply = await generate_assistant_reply(
        session,
        telegram_id=payload.telegram_id,
        message=payload.message,
    )
    logger.info(
        "tg_assistant_response",
        telegram_id=payload.telegram_id,
        source=reply.get("source"),
    )
    return TelegramAssistantReplyResponse(**reply)
