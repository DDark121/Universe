from __future__ import annotations

import asyncio
import csv
import hashlib
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from openpyxl import Workbook
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.pagination import PaginationMeta
from app.core.security import generate_temp_password, hash_password
from app.core.time import utc_now
from app.db.enums import (
    AIImportDraftStatus,
    AIImportMode,
    AttendanceStatus,
    BindingRequestStatus,
    BroadcastScope,
    DeliveryStatus,
    ImportJobType,
    JobStatus,
    RoleCode,
)
from app.db.models import (
    AbsenceReason,
    AIImportDraft,
    AttendanceRecord,
    BiometricDevice,
    BiometricEvent,
    Broadcast,
    BroadcastRecipient,
    Discipline,
    EscalationEvent,
    EscalationRule,
    ExportJob,
    Faculty,
    Group,
    GroupTelegramChat,
    ImportJob,
    InviteCode,
    Lesson,
    RatingSnapshot,
    RiskCard,
    Role,
    Stream,
    StudentBiometric,
    StudentGroupMembership,
    SystemSetting,
    TeacherAssignment,
    TelegramAccount,
    TelegramBindingRequest,
    TutorGroupAssignment,
    User,
)
from app.schemas.admin import (
    AdminAssistantReplyRequest,
    AdminAssistantReplyResponse,
    AssignmentCreateRequest,
    AssignmentUpdateRequest,
    BindingDecisionRequest,
    BiometricDeviceCreateRequest,
    BiometricDeviceUpdateRequest,
    DisciplineCreateRequest,
    DisciplineUpdateRequest,
    EscalationRuleRequest,
    EscalationRuleUpdateRequest,
    ExportJobCreateRequest,
    FacultyCreateRequest,
    FacultyUpdateRequest,
    FaqCategoryCreateRequest,
    FaqCategoryUpdateRequest,
    FaqItemCreateRequest,
    FaqItemUpdateRequest,
    GroupCreateRequest,
    GroupUpdateRequest,
    ImportJobCreateRequest,
    InviteCodeCreateRequest,
    InviteCodeResponse,
    JobResponse,
    LessonCreateRequest,
    LessonStatusUpdateRequest,
    LessonUpdateRequest,
    RatingConfigRequest,
    StreamCreateRequest,
    StreamUpdateRequest,
    StudentBiometricCreateRequest,
    StudentBiometricUpdateRequest,
    StudentTransferRequest,
    SystemSettingRequest,
    TutorAssignmentCreateRequest,
    TutorAssignmentUpdateRequest,
    TutorBroadcastRequest,
    UserCreateRequest,
    UserRolesUpdateRequest,
    UserUpdateRequest,
)
from app.schemas.ai_import import AIImportDraftUpdateRequest, AIImportWizardRequest
from app.schemas.common import ApiMessage
from app.services.ai_imports import (
    AIImportWizard,
    apply_ai_import_draft,
    reject_ai_import_draft,
    save_ai_import_source,
    serialize_ai_import_draft,
    update_ai_import_draft_payload,
)
from app.services.audit import log_audit
from app.services.faq_ai import (
    generate_panel_assistant_reply,
    get_faq_index_status_async,
    list_faq_categories_async,
    list_faq_item_rows_async,
)
from app.services.notifications import enqueue_notification
from app.services.reports import attendance_summary
from app.services.system_settings import resolve_lesson_window_config
from app.tasks.jobs import (
    process_ai_import_draft,
    process_export_job,
    process_import_job,
)

router = APIRouter()
settings = get_settings()
MAX_PAGE_SIZE = 500


def _pagination_meta(page: int, page_size: int, total: int) -> PaginationMeta:
    return PaginationMeta(page=page, page_size=page_size, total=total)


def _validate_ai_wizard(mode: AIImportMode, wizard: AIImportWizardRequest) -> AIImportWizard:
    parsed = AIImportWizard.model_validate(wizard.model_dump())
    if mode != AIImportMode.USERS and (
        not parsed.term_start or not parsed.term_end or not parsed.first_week_parity
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="term_start, term_end and first_week_parity are required for schedule imports",
        )
    if parsed.term_start and parsed.term_end and parsed.term_end < parsed.term_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="term_end must be greater than term_start")
    return parsed


async def _paginate_scalars(
    session: AsyncSession,
    stmt,
    page: int,
    page_size: int,
):
    total = int((await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one())
    rows = (
        await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return rows, total


def _paginate_list(items: list[Any], page: int, page_size: int) -> tuple[list[Any], int]:
    total = len(items)
    start = (page - 1) * page_size
    return items[start : start + page_size], total


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_bytes(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _write_import_template(file_path: Path, format: str, columns: list[str]) -> None:
    if format == "csv":
        with file_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
        return

    wb = Workbook()
    ws = wb.active
    ws.title = file_path.stem.removesuffix("_template")
    ws.append(columns)
    wb.save(file_path)


async def _active_tutor_group_ids(session: AsyncSession, tutor_user_id: UUID) -> list[UUID]:
    rows = (
        await session.execute(
            select(TutorGroupAssignment.group_id).where(
                TutorGroupAssignment.tutor_user_id == tutor_user_id,
                TutorGroupAssignment.is_active.is_(True),
            )
        )
    ).all()
    return [row[0] for row in rows]


def _is_admin(user: User) -> bool:
    return any(role.code == RoleCode.ADMIN for role in user.roles)


def _date_end_exclusive(value: date) -> date:
    return value + timedelta(days=1)


def _student_period_score(
    *,
    total: int,
    present: int,
    late: int,
    absent: int,
    unexcused_absent: int,
    rating_score: float | None,
    risk_score: float | None,
) -> float:
    if total <= 0:
        base_score = rating_score if rating_score is not None else 0
    else:
        attended = present + late
        attendance_pct = attended / total * 100
        punctuality_pct = present / total * 100
        penalty = late * 8 + absent * 10 + unexcused_absent * 18
        discipline_score = max(0, 100 - penalty)
        base_score = attendance_pct * 0.6 + punctuality_pct * 0.25 + discipline_score * 0.15

    if risk_score is not None:
        base_score = min(base_score, risk_score)
    return round(max(0, min(100, base_score)), 2)


def _student_analytics_status(score: float, *, total: int, late: int, unexcused_absent: int) -> str:
    if total <= 0:
        return "no_data"
    if score < 60 or unexcused_absent >= 3 or late >= 4:
        return "critical"
    if score < 75 or unexcused_absent >= 1 or late >= 2:
        return "watch"
    return "stable"


async def _ensure_unique_user_contacts(
    session: AsyncSession,
    *,
    username: str | None = None,
    email: str | None = None,
    phone_number: str | None = None,
    exclude_user_id: UUID | None = None,
) -> None:
    checks = (
        ("username", username, "Username already exists"),
        ("email", email, "Email already exists"),
        ("phone_number", phone_number, "Phone number already exists"),
    )
    for field_name, value, message in checks:
        if value is None:
            continue
        field = getattr(User, field_name)
        stmt = select(User.id).where(field == value)
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        if (await session.execute(stmt)).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


async def _sync_group_telegram_chat(
    session: AsyncSession,
    *,
    group_id: UUID,
    telegram_chat_id: int | None,
    title: str | None,
    is_active: bool = True,
    clear: bool = False,
) -> None:
    row = (
        await session.execute(select(GroupTelegramChat).where(GroupTelegramChat.group_id == group_id))
    ).scalar_one_or_none()
    if clear:
        if row:
            await session.delete(row)
        return
    if telegram_chat_id is None:
        return
    if row:
        row.telegram_chat_id = telegram_chat_id
        row.title = title
        row.is_active = is_active
        return
    session.add(
        GroupTelegramChat(
            group_id=group_id,
            telegram_chat_id=telegram_chat_id,
            title=title,
            is_active=is_active,
        )
    )


@router.post("/users")
async def create_user(
    payload: UserCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_unique_user_contacts(
        session,
        username=payload.username,
        email=payload.email,
        phone_number=payload.phone_number,
    )

    roles_stmt = select(Role).where(Role.code.in_(payload.roles))
    roles = (await session.execute(roles_stmt)).scalars().all()
    if len(roles) != len(payload.roles):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Some roles were not found")

    temp_password = generate_temp_password()
    user = User(
        username=payload.username,
        email=payload.email,
        phone_number=payload.phone_number,
        full_name=payload.full_name,
        password_hash=hash_password(temp_password),
        must_change_password=True,
        roles=roles,
    )
    session.add(user)
    await session.flush()

    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.user_create",
        entity_type="user",
        entity_id=str(user.id),
        details={"roles": [r.code.value for r in roles]},
    )
    await session.commit()
    return {
        "id": user.id,
        "username": user.username,
        "phone_number": user.phone_number,
        "temp_password": temp_password,
        "roles": [r.code.value for r in roles],
    }


@router.get("/users")
async def list_users(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    sort: str = Query(default="-created_at"),
    role: RoleCode | None = None,
    group_id: UUID | None = None,
    search: str | None = None,
):
    stmt = select(User).options(selectinload(User.roles))

    allowed_group_ids: list[UUID] | None = None
    if not _is_admin(current_user):
        allowed_group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not allowed_group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        if group_id and group_id not in allowed_group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        if not group_id:
            stmt = stmt.join(StudentGroupMembership, StudentGroupMembership.student_id == User.id).where(
                StudentGroupMembership.group_id.in_(allowed_group_ids),
                or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= date.today()),
            )

    if role:
        stmt = stmt.join(User.roles).where(Role.code == role)
    if group_id:
        stmt = stmt.join(StudentGroupMembership, StudentGroupMembership.student_id == User.id).where(
            StudentGroupMembership.group_id == group_id,
            or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= date.today()),
        )
    if search:
        search_like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.username).like(search_like),
                func.lower(User.full_name).like(search_like),
                func.lower(func.coalesce(User.email, "")).like(search_like),
                func.lower(func.coalesce(User.phone_number, "")).like(search_like),
            )
        )
    sort_map = {
        "created_at": User.created_at.asc(),
        "-created_at": User.created_at.desc(),
        "username": User.username.asc(),
        "-username": User.username.desc(),
        "full_name": User.full_name.asc(),
        "-full_name": User.full_name.desc(),
    }
    stmt = stmt.order_by(sort_map.get(sort, User.created_at.desc())).distinct()
    users, total = await _paginate_scalars(session, stmt, page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "email": u.email,
                "phone_number": u.phone_number,
                "is_active": u.is_active,
                "is_archived": u.is_archived,
                "roles": [r.code.value for r in u.roles],
            }
            for u in users
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = payload.model_dump(exclude_none=True)
    await _ensure_unique_user_contacts(
        session,
        email=update_data.get("email"),
        phone_number=update_data.get("phone_number"),
        exclude_user_id=user_id,
    )
    for key, value in update_data.items():
        setattr(user, key, value)
    if payload.is_archived is True:
        user.archived_at = utc_now()

    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.user_update",
        entity_type="user",
        entity_id=str(user_id),
        details=update_data,
    )
    await session.commit()
    return {"message": "updated"}


@router.patch("/users/{user_id}/roles", response_model=ApiMessage)
async def update_user_roles(
    user_id: UUID,
    payload: UserRolesUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    user = (
        await session.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    roles = (await session.execute(select(Role).where(Role.code.in_(payload.roles)))).scalars().all()
    if len(roles) != len(payload.roles):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Some roles were not found")

    user.roles = roles
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.user_roles_update",
        entity_type="user",
        entity_id=str(user_id),
        details={"roles": [r.code.value for r in roles]},
    )
    await session.commit()
    return ApiMessage(message="Roles updated")


@router.get("/roles")
async def list_roles(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    rows = (await session.execute(select(Role).order_by(Role.code.asc()))).scalars().all()
    return [
        {
            "id": row.id,
            "code": row.code.value,
            "name": "Тьютор" if row.code == RoleCode.CURATOR else row.name,
        }
        for row in rows
    ]


@router.post("/faculties")
async def create_faculty(
    payload: FacultyCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = Faculty(**payload.model_dump())
    session.add(row)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.faculty_create",
        entity_type="faculty",
        entity_id=str(row.id),
    )
    await session.commit()
    await session.refresh(row)
    return {"id": row.id, "code": row.code, "name": row.name, "is_archived": row.is_archived}


@router.get("/faculties")
async def list_faculties(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(Faculty)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        faculty_ids = (
            await session.execute(select(Group.faculty_id).where(Group.id.in_(group_ids), Group.faculty_id.is_not(None)))
        ).all()
        faculty_ids_values = [row[0] for row in faculty_ids]
        if not faculty_ids_values:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stmt = stmt.where(Faculty.id.in_(faculty_ids_values))
    rows, total = await _paginate_scalars(session, stmt.order_by(Faculty.code.asc()), page=page, page_size=page_size)
    return {
        "items": [{"id": row.id, "code": row.code, "name": row.name, "is_archived": row.is_archived} for row in rows],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/faculties/{faculty_id}")
async def update_faculty(
    faculty_id: UUID,
    payload: FacultyUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(Faculty).where(Faculty.id == faculty_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.faculty_update",
        entity_type="faculty",
        entity_id=str(faculty_id),
        details=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    return {"id": row.id, "code": row.code, "name": row.name, "is_archived": row.is_archived}


@router.post("/streams")
async def create_stream(
    payload: StreamCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = Stream(**payload.model_dump())
    session.add(row)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.stream_create",
        entity_type="stream",
        entity_id=str(row.id),
    )
    await session.commit()
    await session.refresh(row)
    return {"id": row.id, "faculty_id": row.faculty_id, "name": row.name, "is_archived": row.is_archived}


@router.get("/streams")
async def list_streams(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    faculty_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(Stream)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stream_ids = (
            await session.execute(select(Group.stream_id).where(Group.id.in_(group_ids), Group.stream_id.is_not(None)))
        ).all()
        stream_ids_values = [row[0] for row in stream_ids]
        if not stream_ids_values:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stmt = stmt.where(Stream.id.in_(stream_ids_values))
    if faculty_id:
        stmt = stmt.where(Stream.faculty_id == faculty_id)
    rows, total = await _paginate_scalars(session, stmt.order_by(Stream.name.asc()), page=page, page_size=page_size)
    return {
        "items": [
            {"id": row.id, "faculty_id": row.faculty_id, "name": row.name, "is_archived": row.is_archived}
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/streams/{stream_id}")
async def update_stream(
    stream_id: UUID,
    payload: StreamUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(Stream).where(Stream.id == stream_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.stream_update",
        entity_type="stream",
        entity_id=str(stream_id),
        details=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    return {"id": row.id, "faculty_id": row.faculty_id, "name": row.name, "is_archived": row.is_archived}


@router.post("/groups")
async def create_group(
    payload: GroupCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    group = Group(
        **payload.model_dump(
            exclude={
                "telegram_chat_id",
                "telegram_chat_title",
            }
        )
    )
    session.add(group)
    await session.flush()
    await _sync_group_telegram_chat(
        session,
        group_id=group.id,
        telegram_chat_id=payload.telegram_chat_id,
        title=payload.telegram_chat_title,
    )
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.group_create",
        entity_type="group",
        entity_id=str(group.id),
    )
    await session.commit()
    await session.refresh(group)
    return {"id": group.id, "code": group.code, "name": group.name}


@router.get("/groups")
async def list_groups(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(Group)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stmt = stmt.where(Group.id.in_(group_ids))

    groups, total = await _paginate_scalars(session, stmt.order_by(Group.code.asc()), page=page, page_size=page_size)
    chats_by_group: dict[UUID, GroupTelegramChat] = {}
    if groups:
        rows = (
            await session.execute(
                select(GroupTelegramChat).where(GroupTelegramChat.group_id.in_([group.id for group in groups]))
            )
        ).scalars().all()
        chats_by_group = {row.group_id: row for row in rows}
    return {
        "items": [
            {
                "id": g.id,
                "code": g.code,
                "name": g.name,
                "is_archived": g.is_archived,
                "faculty_id": g.faculty_id,
                "stream_id": g.stream_id,
                "is_subgroup": g.is_subgroup,
                "parent_group_id": g.parent_group_id,
                "window_start_offset_override_minutes": g.window_start_offset_override_minutes,
                "window_duration_override_minutes": g.window_duration_override_minutes,
                "late_threshold_override_minutes": g.late_threshold_override_minutes,
                "telegram_chat_id": chats_by_group.get(g.id).telegram_chat_id if chats_by_group.get(g.id) else None,
                "telegram_chat_title": chats_by_group.get(g.id).title if chats_by_group.get(g.id) else None,
                "telegram_chat_is_active": chats_by_group.get(g.id).is_active if chats_by_group.get(g.id) else None,
            }
            for g in groups
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: UUID,
    payload: GroupUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    group = (await session.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    for key, value in payload.model_dump(
        exclude_none=True,
        exclude={"telegram_chat_id", "telegram_chat_title", "telegram_chat_is_active"},
    ).items():
        setattr(group, key, value)
    if "telegram_chat_id" in payload.model_fields_set:
        await _sync_group_telegram_chat(
            session,
            group_id=group.id,
            telegram_chat_id=payload.telegram_chat_id,
            title=payload.telegram_chat_title,
            is_active=payload.telegram_chat_is_active if payload.telegram_chat_is_active is not None else True,
            clear=payload.telegram_chat_id is None,
        )
    elif "telegram_chat_title" in payload.model_fields_set or "telegram_chat_is_active" in payload.model_fields_set:
        chat = (
            await session.execute(select(GroupTelegramChat).where(GroupTelegramChat.group_id == group.id))
        ).scalar_one_or_none()
        if chat:
            if "telegram_chat_title" in payload.model_fields_set:
                chat.title = payload.telegram_chat_title
            if "telegram_chat_is_active" in payload.model_fields_set and payload.telegram_chat_is_active is not None:
                chat.is_active = payload.telegram_chat_is_active
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.group_update",
        entity_type="group",
        entity_id=str(group_id),
        details=payload.model_dump(exclude_none=True, mode="json"),
    )
    await session.commit()
    group_chat = (
        await session.execute(select(GroupTelegramChat).where(GroupTelegramChat.group_id == group.id))
    ).scalar_one_or_none()
    return {
        "id": group.id,
        "code": group.code,
        "name": group.name,
        "is_archived": group.is_archived,
        "faculty_id": group.faculty_id,
        "stream_id": group.stream_id,
        "window_start_offset_override_minutes": group.window_start_offset_override_minutes,
        "window_duration_override_minutes": group.window_duration_override_minutes,
        "late_threshold_override_minutes": group.late_threshold_override_minutes,
        "telegram_chat_id": group_chat.telegram_chat_id if group_chat else None,
        "telegram_chat_title": group_chat.title if group_chat else None,
        "telegram_chat_is_active": group_chat.is_active if group_chat else None,
    }


@router.post("/disciplines")
async def create_discipline(
    payload: DisciplineCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    discipline = Discipline(**payload.model_dump())
    session.add(discipline)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.discipline_create",
        entity_type="discipline",
        entity_id=str(discipline.id),
    )
    await session.commit()
    await session.refresh(discipline)
    return {"id": discipline.id, "code": discipline.code, "name": discipline.name}


@router.get("/disciplines")
async def list_disciplines(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR, RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(Discipline)
    user_roles = {role.code for role in current_user.roles}
    if RoleCode.ADMIN not in user_roles:
        if RoleCode.TEACHER in user_roles:
            stmt = stmt.join(
                TeacherAssignment,
                TeacherAssignment.discipline_id == Discipline.id,
            ).where(
                TeacherAssignment.teacher_id == current_user.id,
                TeacherAssignment.is_active.is_(True),
            )
        else:
            group_ids = await _active_tutor_group_ids(session, current_user.id)
            if not group_ids:
                return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
            stmt = stmt.join(
                TeacherAssignment,
                TeacherAssignment.discipline_id == Discipline.id,
            ).where(
                TeacherAssignment.group_id.in_(group_ids),
                TeacherAssignment.is_active.is_(True),
            )
    stmt = stmt.order_by(Discipline.name.asc()).distinct()
    items, total = await _paginate_scalars(session, stmt, page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": d.id,
                "code": d.code,
                "name": d.name,
                "is_archived": d.is_archived,
                "window_start_offset_override_minutes": d.window_start_offset_override_minutes,
                "window_duration_override_minutes": d.window_duration_override_minutes,
                "late_threshold_override_minutes": d.late_threshold_override_minutes,
            }
            for d in items
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/disciplines/{discipline_id}")
async def update_discipline(
    discipline_id: UUID,
    payload: DisciplineUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(Discipline).where(Discipline.id == discipline_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discipline not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.discipline_update",
        entity_type="discipline",
        entity_id=str(discipline_id),
        details=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "is_archived": row.is_archived,
        "window_start_offset_override_minutes": row.window_start_offset_override_minutes,
        "window_duration_override_minutes": row.window_duration_override_minutes,
        "late_threshold_override_minutes": row.late_threshold_override_minutes,
    }


@router.post("/assignments")
async def create_assignment(
    payload: AssignmentCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    assignment = TeacherAssignment(**payload.model_dump())
    session.add(assignment)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.assignment_create",
        entity_type="teacher_assignment",
        entity_id=str(assignment.id),
    )
    await session.commit()
    await session.refresh(assignment)
    return {"id": assignment.id}


@router.get("/assignments")
async def list_assignments(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(TeacherAssignment)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stmt = stmt.where(TeacherAssignment.group_id.in_(group_ids))
    rows, total = await _paginate_scalars(session, stmt.order_by(TeacherAssignment.created_at.desc()), page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": r.id,
                "teacher_id": r.teacher_id,
                "discipline_id": r.discipline_id,
                "group_id": r.group_id,
                "is_active": r.is_active,
            }
            for r in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/assignments/{assignment_id}")
async def update_assignment(
    assignment_id: UUID,
    payload: AssignmentUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (
        await session.execute(select(TeacherAssignment).where(TeacherAssignment.id == assignment_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.assignment_update",
        entity_type="teacher_assignment",
        entity_id=str(assignment_id),
        details=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    return {
        "id": row.id,
        "teacher_id": row.teacher_id,
        "discipline_id": row.discipline_id,
        "group_id": row.group_id,
        "is_active": row.is_active,
    }


@router.delete("/assignments/{assignment_id}", response_model=ApiMessage)
async def archive_assignment(
    assignment_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    row = (
        await session.execute(select(TeacherAssignment).where(TeacherAssignment.id == assignment_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    row.is_active = False
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.assignment_archive",
        entity_type="teacher_assignment",
        entity_id=str(assignment_id),
    )
    await session.commit()
    return ApiMessage(message="Assignment archived")


@router.post("/tutor-assignments")
async def create_tutor_assignment(
    payload: TutorAssignmentCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    tutor_user = (
        await session.execute(select(User).where(User.id == payload.tutor_user_id).options(selectinload(User.roles)))
    ).scalar_one_or_none()
    if not tutor_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tutor user not found")
    if RoleCode.CURATOR not in {role.code for role in tutor_user.roles}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User does not have curator role")

    row = TutorGroupAssignment(
        tutor_user_id=payload.tutor_user_id,
        group_id=payload.group_id,
        is_active=True,
    )
    session.add(row)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.tutor_assignment_create",
        entity_type="tutor_group_assignment",
        entity_id=str(row.id),
        details=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(row)
    return {"id": row.id, "tutor_user_id": row.tutor_user_id, "group_id": row.group_id, "is_active": row.is_active}


@router.get("/tutor-assignments")
async def list_tutor_assignments(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    tutor_user_id: UUID | None = None,
    group_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(TutorGroupAssignment)
    if tutor_user_id:
        stmt = stmt.where(TutorGroupAssignment.tutor_user_id == tutor_user_id)
    if group_id:
        stmt = stmt.where(TutorGroupAssignment.group_id == group_id)
    rows, total = await _paginate_scalars(
        session,
        stmt.order_by(TutorGroupAssignment.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": row.id,
                "tutor_user_id": row.tutor_user_id,
                "group_id": row.group_id,
                "is_active": row.is_active,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/tutor-assignments/{assignment_id}")
async def update_tutor_assignment(
    assignment_id: UUID,
    payload: TutorAssignmentUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (
        await session.execute(select(TutorGroupAssignment).where(TutorGroupAssignment.id == assignment_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tutor assignment not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.tutor_assignment_update",
        entity_type="tutor_group_assignment",
        entity_id=str(assignment_id),
        details=payload.model_dump(mode="json", exclude_none=True),
    )
    await session.commit()
    return {"id": row.id, "tutor_user_id": row.tutor_user_id, "group_id": row.group_id, "is_active": row.is_active}


@router.delete("/tutor-assignments/{assignment_id}", response_model=ApiMessage)
async def delete_tutor_assignment(
    assignment_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    row = (
        await session.execute(select(TutorGroupAssignment).where(TutorGroupAssignment.id == assignment_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tutor assignment not found")
    await session.delete(row)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.tutor_assignment_delete",
        entity_type="tutor_group_assignment",
        entity_id=str(assignment_id),
    )
    await session.commit()
    return ApiMessage(message="Tutor assignment deleted")


@router.get("/tutor/groups")
async def list_tutor_groups(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    tutor_user_id: UUID | None = None,
):
    if _is_admin(current_user):
        if tutor_user_id:
            group_ids = await _active_tutor_group_ids(session, tutor_user_id)
            if not group_ids:
                return []
            rows = (await session.execute(select(Group).where(Group.id.in_(group_ids)).order_by(Group.code.asc()))).scalars().all()
            return [{"id": row.id, "code": row.code, "name": row.name} for row in rows]
        rows = (await session.execute(select(Group).order_by(Group.code.asc()))).scalars().all()
        return [{"id": row.id, "code": row.code, "name": row.name} for row in rows]

    group_ids = await _active_tutor_group_ids(session, current_user.id)
    if not group_ids:
        return []
    rows = (await session.execute(select(Group).where(Group.id.in_(group_ids)).order_by(Group.code.asc()))).scalars().all()
    return [{"id": row.id, "code": row.code, "name": row.name} for row in rows]


@router.post("/tutor/broadcasts")
async def tutor_broadcast(
    payload: TutorBroadcastRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    if not _is_admin(current_user):
        allowed_group_ids = await _active_tutor_group_ids(session, current_user.id)
        if payload.group_id not in allowed_group_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this group")

    broadcast = Broadcast(
        sender_id=current_user.id,
        scope=BroadcastScope.GROUP,
        group_id=payload.group_id,
        message=payload.message,
    )
    session.add(broadcast)
    await session.flush()

    members = (
        await session.execute(
            select(StudentGroupMembership.student_id)
            .where(StudentGroupMembership.group_id == payload.group_id, StudentGroupMembership.end_date.is_(None))
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
            event_type="tutor_broadcast",
            recipient_user_id=student_id,
            recipient_telegram_id=telegram,
            payload={"message": payload.message, "group_id": str(payload.group_id)},
            idempotency_key=f"tutor_broadcast:{broadcast.id}:{student_id}",
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
            event_type="tutor_broadcast",
            recipient_user_id=None,
            recipient_telegram_id=group_chat.telegram_chat_id,
            payload={"message": payload.message, "group_id": str(payload.group_id), "delivery": "group_chat"},
            idempotency_key=(
                f"tutor_group_chat_broadcast:{payload.group_id}:{group_chat.telegram_chat_id}:"
                f"{hashlib.sha256(payload.message.encode('utf-8')).hexdigest()[:16]}"
            ),
        )

    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.tutor_broadcast",
        entity_type="broadcast",
        entity_id=str(broadcast.id),
        details={"group_id": str(payload.group_id), "recipients": len(members), "group_chat": bool(group_chat)},
    )
    await session.commit()
    return {"broadcast_id": broadcast.id, "recipients": len(members), "group_chat_queued": bool(group_chat)}


@router.post("/assistant/reply", response_model=AdminAssistantReplyResponse)
async def admin_assistant_reply(
    payload: AdminAssistantReplyRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
) -> AdminAssistantReplyResponse:
    reply = await generate_panel_assistant_reply(
        session,
        user=current_user,
        message=payload.message,
        current_path=payload.current_path,
        history=[item.model_dump() for item in payload.history],
    )
    return AdminAssistantReplyResponse(**reply)


@router.post("/biometric/devices")
async def create_biometric_device(
    payload: BiometricDeviceCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    existing = (
        await session.execute(select(BiometricDevice).where(BiometricDevice.device_id == payload.device_id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Biometric device already exists")

    secret_hash = hashlib.sha256(payload.secret.encode("utf-8")).hexdigest()
    row = BiometricDevice(
        device_id=payload.device_id,
        secret_hash=secret_hash,
        description=payload.description,
        allowed_ips=payload.allowed_ips,
        is_active=payload.is_active,
    )
    session.add(row)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.biometric_device_create",
        entity_type="biometric_device",
        entity_id=str(row.id),
        details={"device_id": payload.device_id},
    )
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "device_id": row.device_id,
        "is_active": row.is_active,
        "description": row.description,
        "allowed_ips": row.allowed_ips,
        "created_at": row.created_at,
    }


@router.get("/biometric/devices")
async def list_biometric_devices(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    rows, total = await _paginate_scalars(
        session,
        select(BiometricDevice).order_by(BiometricDevice.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": row.id,
                "device_id": row.device_id,
                "is_active": row.is_active,
                "description": row.description,
                "allowed_ips": row.allowed_ips,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/biometric/devices/{device_id}")
async def update_biometric_device(
    device_id: UUID,
    payload: BiometricDeviceUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(BiometricDevice).where(BiometricDevice.id == device_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Biometric device not found")
    values = payload.model_dump(exclude_none=True)
    secret_raw = values.pop("secret", None)
    for key, value in values.items():
        setattr(row, key, value)
    if secret_raw:
        row.secret_hash = hashlib.sha256(secret_raw.encode("utf-8")).hexdigest()
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.biometric_device_update",
        entity_type="biometric_device",
        entity_id=str(device_id),
        details={**values, **({"secret": "updated"} if secret_raw else {})},
    )
    await session.commit()
    return {
        "id": row.id,
        "device_id": row.device_id,
        "is_active": row.is_active,
        "description": row.description,
        "allowed_ips": row.allowed_ips,
    }


@router.post("/biometric/students")
async def create_student_biometric(
    payload: StudentBiometricCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = StudentBiometric(
        student_id=payload.student_id,
        fingerprint_hash=payload.fingerprint_hash,
        is_active=payload.is_active,
    )
    session.add(row)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.student_biometric_create",
        entity_type="student_biometric",
        entity_id=str(row.id),
        details=payload.model_dump(mode="json"),
    )
    await session.commit()
    await session.refresh(row)
    return {"id": row.id, "student_id": row.student_id, "is_active": row.is_active}


@router.get("/biometric/students")
async def list_student_biometrics(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    student_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(StudentBiometric)
    if student_id:
        stmt = stmt.where(StudentBiometric.student_id == student_id)
    rows, total = await _paginate_scalars(
        session,
        stmt.order_by(StudentBiometric.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": row.id,
                "student_id": row.student_id,
                "fingerprint_hash": row.fingerprint_hash,
                "is_active": row.is_active,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/biometric/students/{biometric_id}")
async def update_student_biometric(
    biometric_id: UUID,
    payload: StudentBiometricUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (
        await session.execute(select(StudentBiometric).where(StudentBiometric.id == biometric_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student biometric not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.student_biometric_update",
        entity_type="student_biometric",
        entity_id=str(biometric_id),
        details=payload.model_dump(mode="json", exclude_none=True),
    )
    await session.commit()
    return {"id": row.id, "student_id": row.student_id, "is_active": row.is_active}


@router.get("/biometric/events")
async def list_biometric_events(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(BiometricEvent).order_by(BiometricEvent.created_at.desc())
    rows, total = await _paginate_scalars(session, stmt, page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": row.id,
                "device_id": row.device_id,
                "scanner_event_id": row.scanner_event_id,
                "lesson_id": row.lesson_id,
                "student_id": row.student_id,
                "success": row.success,
                "reason": row.reason,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.post("/lessons")
async def create_lesson(
    payload: LessonCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    window_config = await resolve_lesson_window_config(
        session,
        group_id=payload.group_id,
        discipline_id=payload.discipline_id,
        explicit={
            "window_start_offset_minutes": payload.window_start_offset_minutes,
            "window_duration_minutes": payload.window_duration_minutes,
            "late_threshold_minutes": payload.late_threshold_minutes,
        },
    )
    lesson = Lesson(
        **payload.model_dump(
            exclude={
                "window_start_offset_minutes",
                "window_duration_minutes",
                "late_threshold_minutes",
            }
        ),
        **window_config,
    )
    session.add(lesson)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.lesson_create",
        entity_type="lesson",
        entity_id=str(lesson.id),
    )
    await session.commit()
    await session.refresh(lesson)
    return {"id": lesson.id}


@router.patch("/lessons/{lesson_id}")
async def update_lesson(
    lesson_id: UUID,
    payload: LessonUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    lesson = (await session.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(lesson, key, value)

    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.lesson_update",
        entity_type="lesson",
        entity_id=str(lesson_id),
        details=changes,
    )
    await session.commit()
    return {"message": "updated"}


@router.patch("/lessons/{lesson_id}/status")
async def update_lesson_status(
    lesson_id: UUID,
    payload: LessonStatusUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    lesson = (await session.execute(select(Lesson).where(Lesson.id == lesson_id))).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    lesson.status = payload.status
    lesson.canceled_reason = payload.canceled_reason
    if payload.rescheduled_from_id:
        lesson.rescheduled_from_id = payload.rescheduled_from_id
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.lesson_status_update",
        entity_type="lesson",
        entity_id=str(lesson_id),
        details=payload.model_dump(mode="json"),
    )

    if payload.status.value in {"canceled", "rescheduled"}:
        recipients = (
            await session.execute(
                select(StudentGroupMembership.student_id)
                .where(
                    StudentGroupMembership.group_id == lesson.group_id,
                    or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= date.today()),
                )
            )
        ).all()
        event_type = "lesson_canceled" if payload.status.value == "canceled" else "lesson_rescheduled"
        for (student_id,) in recipients:
            telegram_id = (
                await session.execute(select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == student_id))
            ).scalar_one_or_none()
            await enqueue_notification(
                session,
                event_type=event_type,
                recipient_user_id=student_id,
                recipient_telegram_id=telegram_id,
                payload={
                    "lesson_id": str(lesson.id),
                    "status": payload.status.value,
                    "reason": payload.canceled_reason,
                },
                idempotency_key=f"{event_type}:{lesson.id}:{student_id}:{payload.status.value}",
            )

    await session.commit()
    return {
        "id": lesson.id,
        "status": lesson.status.value,
        "canceled_reason": lesson.canceled_reason,
        "rescheduled_from_id": lesson.rescheduled_from_id,
    }


@router.post("/lessons/import", response_model=JobResponse)
async def import_lessons_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only csv/xlsx files are supported")

    imports_dir = Path("/tmp/universe-imports")
    await asyncio.to_thread(_ensure_directory, imports_dir)
    file_path = imports_dir / f"{uuid4().hex}{ext}"
    content = await file.read()
    await asyncio.to_thread(_write_bytes, file_path, content)

    if ext == ".csv":
        # Basic structural check before scheduling async import.
        csv.DictReader(StringIO(content.decode("utf-8", errors="ignore")))

    job = ImportJob(
        created_by=current_user.id,
        job_type=ImportJobType.SCHEDULE,
        file_name=file.filename or file_path.name,
        file_path=str(file_path),
        status=JobStatus.PENDING,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    process_import_job.delay(str(job.id))
    return JobResponse(id=job.id, status=job.status, created_at=job.created_at)


@router.get("/lessons")
async def list_lessons(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = select(Lesson)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stmt = stmt.where(Lesson.group_id.in_(group_ids))
    if date_from:
        stmt = stmt.where(Lesson.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Lesson.starts_at < _date_end_exclusive(date_to))
    lessons, total = await _paginate_scalars(session, stmt.order_by(Lesson.starts_at.asc()), page=page, page_size=page_size)
    return {
        "items": [
            {
                "id": lesson.id,
                "group_id": lesson.group_id,
                "discipline_id": lesson.discipline_id,
                "teacher_id": lesson.teacher_id,
                "starts_at": lesson.starts_at,
                "ends_at": lesson.ends_at,
                "status": lesson.status.value,
                "room": lesson.room,
                "window_start_offset_minutes": lesson.window_start_offset_minutes,
                "window_duration_minutes": lesson.window_duration_minutes,
                "late_threshold_minutes": lesson.late_threshold_minutes,
            }
            for lesson in lessons
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.post("/invite-codes", response_model=InviteCodeResponse)
async def create_invite_code(
    payload: InviteCodeCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> InviteCodeResponse:
    code = f"INV-{uuid4().hex[:10].upper()}"
    invite = InviteCode(code=code, created_by=current_user.id, **payload.model_dump())
    session.add(invite)
    await session.commit()
    return InviteCodeResponse(code=invite.code, expires_at=invite.expires_at, max_activations=invite.max_activations)


@router.get("/invite-codes")
async def list_invite_codes(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    rows, total = await _paginate_scalars(
        session,
        select(InviteCode).order_by(InviteCode.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": row.id,
                "code": row.code,
                "role_code": row.role_code.value,
                "group_id": row.group_id,
                "discipline_id": row.discipline_id,
                "expires_at": row.expires_at,
                "max_activations": row.max_activations,
                "activation_count": row.activation_count,
                "is_active": row.is_active,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/binding-requests")
async def list_binding_requests(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    rows, total = await _paginate_scalars(
        session,
        select(TelegramBindingRequest).order_by(TelegramBindingRequest.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": r.id,
                "telegram_id": r.telegram_id,
                "telegram_username": r.telegram_username,
                "full_name": r.full_name,
                "group_code": r.group_code,
                "note": r.note,
                "status": r.status.value,
                "requested_user_id": r.requested_user_id,
                "created_at": r.created_at,
                "resolved_at": r.resolved_at,
            }
            for r in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.post("/binding-requests/decision", response_model=ApiMessage)
async def decide_binding_request(
    payload: BindingDecisionRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    req = (
        await session.execute(select(TelegramBindingRequest).where(TelegramBindingRequest.id == payload.request_id))
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if payload.approve:
        tg_exists = (
            await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == req.telegram_id))
        ).scalar_one_or_none()
        if tg_exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Telegram ID already linked")

        user_exists = (
            await session.execute(select(TelegramAccount).where(TelegramAccount.user_id == payload.user_id))
        ).scalar_one_or_none()
        if user_exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already has Telegram binding")

        session.add(
            TelegramAccount(
                user_id=payload.user_id,
                telegram_id=req.telegram_id,
                username=req.telegram_username,
                first_name=req.full_name,
            )
        )
        req.status = BindingRequestStatus.APPROVED
        req.requested_user_id = payload.user_id
    else:
        req.status = BindingRequestStatus.REJECTED

    req.resolved_by = current_user.id
    req.resolved_at = utc_now()
    await session.commit()
    return ApiMessage(message="Binding decision saved")


@router.put("/settings/{key}", response_model=ApiMessage)
async def set_setting(
    key: str,
    payload: SystemSettingRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    row = (await session.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    if row:
        row.value = payload.value
        row.updated_by = current_user.id
    else:
        session.add(SystemSetting(key=key, value=payload.value, updated_by=current_user.id))
    await session.commit()
    return ApiMessage(message="Setting updated")


@router.get("/settings/{key}")
async def get_setting(
    key: str,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")
    return {"key": row.key, "value": row.value}


@router.post("/faq/categories")
async def create_faq_category(
    payload: FaqCategoryCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    _ = (payload, current_user, session)
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="FAQ is managed from data/*.md files and is read-only in the admin panel.",
    )


@router.patch("/faq/categories/{category_id}")
async def update_faq_category(
    category_id: UUID,
    payload: FaqCategoryUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    _ = (category_id, payload, current_user, session)
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="FAQ is managed from data/*.md files and is read-only in the admin panel.",
    )


@router.get("/faq/categories")
async def list_faq_categories(
    include_inactive: bool = False,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR, RoleCode.STUDENT, RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    _ = (include_inactive, current_user, session)
    categories, total = _paginate_list(await list_faq_categories_async(), page, page_size)
    return {
        "items": categories,
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/faq/status")
async def get_faq_status(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
):
    _ = current_user
    return await get_faq_index_status_async()


@router.post("/faq/items")
async def create_faq_item(
    payload: FaqItemCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    _ = (payload, current_user, session)
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="FAQ is managed from data/*.md files and is read-only in the admin panel.",
    )


@router.patch("/faq/items/{item_id}")
async def update_faq_item(
    item_id: UUID,
    payload: FaqItemUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    _ = (item_id, payload, current_user, session)
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="FAQ is managed from data/*.md files and is read-only in the admin panel.",
    )


@router.get("/faq/items")
async def list_faq_items(
    query: str | None = None,
    include_inactive: bool = False,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR, RoleCode.STUDENT, RoleCode.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    _ = (include_inactive, current_user, session)
    rows, total = _paginate_list(await list_faq_item_rows_async(query), page, page_size)
    return {
        "items": [
            {
                "id": row["id"],
                "category_id": row["category_id"],
                "question": row["question"],
                "answer": row["answer"],
                "keywords": row["keywords"],
                "is_active": row["is_active"],
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.put("/rating/config", response_model=ApiMessage)
async def update_rating_config(
    payload: RatingConfigRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    from app.db.models import RatingConfig

    row = (await session.execute(select(RatingConfig).limit(1))).scalar_one_or_none()
    if not row:
        row = RatingConfig(**payload.model_dump(), updated_by=current_user.id)
        session.add(row)
    else:
        for k, v in payload.model_dump().items():
            setattr(row, k, v)
        row.updated_by = current_user.id

    await session.commit()
    return ApiMessage(message="Rating config updated")


@router.get("/rating/config")
async def get_rating_config(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    from app.db.models import RatingConfig

    row = (await session.execute(select(RatingConfig).limit(1))).scalar_one_or_none()
    if not row:
        return None
    return {
        "attendance_weight": float(row.attendance_weight),
        "late_weight": float(row.late_weight),
        "unexcused_absence_weight": float(row.unexcused_absence_weight),
        "activity_weight": float(row.activity_weight),
        "updated_at": row.updated_at,
    }


@router.post("/escalation-rules")
async def create_escalation_rule(
    payload: EscalationRuleRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    rule = EscalationRule(**payload.model_dump())
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return {"id": rule.id}


@router.get("/escalation-rules")
async def list_escalation_rules(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    rules, total = await _paginate_scalars(
        session,
        select(EscalationRule).order_by(EscalationRule.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "threshold_unexcused_absences": r.threshold_unexcused_absences,
                "threshold_lates": r.threshold_lates,
                "min_rating": r.min_rating,
                "is_active": r.is_active,
            }
            for r in rules
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.patch("/escalation-rules/{rule_id}")
async def update_escalation_rule(
    rule_id: UUID,
    payload: EscalationRuleUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    rule = (
        await session.execute(select(EscalationRule).where(EscalationRule.id == rule_id))
    ).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation rule not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(rule, key, value)
    await session.commit()
    return {
        "id": rule.id,
        "name": rule.name,
        "threshold_unexcused_absences": rule.threshold_unexcused_absences,
        "threshold_lates": rule.threshold_lates,
        "min_rating": rule.min_rating,
        "is_active": rule.is_active,
    }


@router.get("/risk/students")
async def list_risk_students(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    faculty_id: UUID | None = None,
    stream_id: UUID | None = None,
    group_id: UUID | None = None,
    discipline_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    current_date = date.today()
    stmt = (
        select(RiskCard, User)
        .join(User, User.id == RiskCard.student_id)
        .where(RiskCard.is_active.is_(True))
    )

    allowed_group_ids: list[UUID] | None = None
    if not _is_admin(current_user):
        allowed_group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not allowed_group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}

    if faculty_id or stream_id or group_id or allowed_group_ids is not None:
        membership_student_ids = select(StudentGroupMembership.student_id).where(
            or_(
                StudentGroupMembership.end_date.is_(None),
                StudentGroupMembership.end_date >= current_date,
            )
        )
        if faculty_id or stream_id:
            membership_student_ids = membership_student_ids.join(
                Group,
                Group.id == StudentGroupMembership.group_id,
            )
        if faculty_id:
            membership_student_ids = membership_student_ids.where(Group.faculty_id == faculty_id)
        if stream_id:
            membership_student_ids = membership_student_ids.where(Group.stream_id == stream_id)
        if group_id:
            membership_student_ids = membership_student_ids.where(StudentGroupMembership.group_id == group_id)
        if allowed_group_ids is not None:
            membership_student_ids = membership_student_ids.where(StudentGroupMembership.group_id.in_(allowed_group_ids))
        stmt = stmt.where(User.id.in_(membership_student_ids))

    if discipline_id or date_from or date_to:
        attendance_student_ids = select(AttendanceRecord.student_id).join(
            Lesson,
            Lesson.id == AttendanceRecord.lesson_id,
        )
        if discipline_id:
            attendance_student_ids = attendance_student_ids.where(Lesson.discipline_id == discipline_id)
        if date_from:
            attendance_student_ids = attendance_student_ids.where(Lesson.starts_at >= date_from)
        if date_to:
            attendance_student_ids = attendance_student_ids.where(Lesson.starts_at < _date_end_exclusive(date_to))
        stmt = stmt.where(User.id.in_(attendance_student_ids.distinct()))

    stmt = stmt.order_by(RiskCard.updated_at.desc())
    total = int((await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one())
    rows = (await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    return {
        "items": [
            {
                "student_id": user.id,
                "student_name": user.full_name,
                "score": float(card.last_score),
                "late_count": card.late_count,
                "unexcused_absence_count": card.unexcused_absence_count,
                "reasons": card.reasons,
            }
            for card, user in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/risk/students/{student_id}")
async def risk_student_detail(
    student_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    user = (await session.execute(select(User).where(User.id == student_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    if not _is_admin(current_user):
        allowed_group_ids = set(await _active_tutor_group_ids(session, current_user.id))
        if not allowed_group_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to student")
        membership_groups = (
            await session.execute(
                select(StudentGroupMembership.group_id).where(
                    StudentGroupMembership.student_id == student_id,
                    or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= date.today()),
                )
            )
        ).all()
        if not any(row[0] in allowed_group_ids for row in membership_groups):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to student")

    card = (
        await session.execute(
            select(RiskCard).where(RiskCard.student_id == student_id, RiskCard.is_active.is_(True))
        )
    ).scalar_one_or_none()


    ratings = (
        await session.execute(
            select(RatingSnapshot)
            .where(RatingSnapshot.student_id == student_id)
            .order_by(RatingSnapshot.calculated_at.desc())
            .limit(20)
        )
    ).scalars().all()
    from app.db.models import RiskForecast

    forecasts = (
        await session.execute(
            select(RiskForecast)
            .where(RiskForecast.student_id == student_id)
            .order_by(RiskForecast.calculated_for_date.desc(), RiskForecast.horizon_days.asc())
            .limit(20)
        )
    ).scalars().all()
    reasons = (
        await session.execute(
            select(AbsenceReason, Lesson)
            .join(Lesson, Lesson.id == AbsenceReason.lesson_id)
            .where(AbsenceReason.student_id == student_id)
            .order_by(AbsenceReason.created_at.desc())
            .limit(30)
        )
    ).all()
    escalations = (
        await session.execute(
            select(EscalationEvent)
            .where(EscalationEvent.student_id == student_id)
            .order_by(EscalationEvent.created_at.desc())
            .limit(30)
        )
    ).scalars().all()
    return {
        "student": {
            "id": user.id,
            "full_name": user.full_name,
            "username": user.username,
            "email": user.email,
            "phone_number": user.phone_number,
        },
        "risk_card": (
            {
                "score": float(card.last_score),
                "late_count": card.late_count,
                "unexcused_absence_count": card.unexcused_absence_count,
                "reasons": card.reasons,
            }
            if card
            else None
        ),
        "ratings": [
            {
                "period_start": row.period_start,
                "period_end": row.period_end,
                "score": float(row.score),
                "attendance_pct": float(row.attendance_pct),
                "late_count": row.late_count,
                "unexcused_absence_count": row.unexcused_absence_count,
                "calculated_at": row.calculated_at,
            }
            for row in ratings
        ],
        "forecasts": [
            {
                "horizon_days": item.horizon_days,
                "period_days": item.period_days,
                "predicted_score": float(item.predicted_score),
                "predicted_late_count": item.predicted_late_count,
                "predicted_unexcused_absence_count": item.predicted_unexcused_absence_count,
                "confidence": float(item.confidence),
                "calculated_for_date": item.calculated_for_date,
                "explain": item.explain,
            }
            for item in forecasts
        ],
        "absence_reasons": [
            {
                "reason_id": reason.id,
                "lesson_id": lesson.id,
                "lesson_starts_at": lesson.starts_at,
                "reason_type": reason.reason_type.value,
                "comment": reason.comment,
                "is_predeclared": reason.is_predeclared,
                "moderation_status": reason.moderation_status.value,
                "moderation_comment": reason.moderation_comment,
                "moderated_at": reason.moderated_at,
            }
            for reason, lesson in reasons
        ],
        "escalations": [
            {
                "id": item.id,
                "status": item.status.value,
                "reason_payload": item.reason_payload,
                "created_at": item.created_at,
                "resolved_at": item.resolved_at,
            }
            for item in escalations
        ],
    }


@router.post("/risk/{student_id}/warn", response_model=ApiMessage)
async def send_risk_warning(
    student_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    if not _is_admin(current_user):
        allowed_group_ids = set(await _active_tutor_group_ids(session, current_user.id))
        membership_groups = (
            await session.execute(
                select(StudentGroupMembership.group_id).where(
                    StudentGroupMembership.student_id == student_id,
                    or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= date.today()),
                )
            )
        ).all()
        if not any(row[0] in allowed_group_ids for row in membership_groups):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to student")

    await enqueue_notification(
        session,
        event_type="risk_warning_manual",
        recipient_user_id=student_id,
        payload={"from": str(current_user.id)},
        idempotency_key=f"manual_risk_warning:{student_id}:{utc_now().isoformat()}",
    )
    await session.commit()
    return ApiMessage(message="Warning queued")


@router.get("/audit/logs")
async def list_audit_logs(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    action: str | None = None,
    actor: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
):
    from app.db.models import AuditLog

    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor_user_id == actor)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    rows = (
        await session.execute(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size))
    ).scalars().all()
    return {
        "items": [
        {
            "id": r.id,
            "actor_user_id": r.actor_user_id,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "details": r.details,
            "created_at": r.created_at,
        }
        for r in rows
        ],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": int(total),
        },
    }


@router.post("/student-transfer", response_model=ApiMessage)
async def transfer_student(
    payload: StudentTransferRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    active_stmt = select(StudentGroupMembership).where(
        StudentGroupMembership.student_id == payload.student_id,
        StudentGroupMembership.end_date.is_(None),
    )
    current = (await session.execute(active_stmt)).scalar_one_or_none()
    if current:
        current.end_date = payload.transfer_date

    session.add(
        StudentGroupMembership(
            student_id=payload.student_id,
            group_id=payload.target_group_id,
            start_date=payload.transfer_date,
            end_date=None,
            is_primary=True,
        )
    )
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="admin.student_transfer",
        entity_type="student_group_membership",
        details=payload.model_dump(mode="json"),
    )
    await session.commit()
    return ApiMessage(message="Student transferred")


@router.post("/imports", response_model=JobResponse)
async def create_import_job(
    payload: ImportJobCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = ImportJob(created_by=current_user.id, **payload.model_dump())
    session.add(job)
    await session.commit()
    await session.refresh(job)
    process_import_job.delay(str(job.id))
    return JobResponse(id=job.id, status=job.status, created_at=job.created_at)


@router.post("/imports/upload")
async def upload_import_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only csv/xlsx files are supported")
    imports_dir = Path("/tmp/universe-imports")
    await asyncio.to_thread(_ensure_directory, imports_dir)
    target = imports_dir / f"{uuid4().hex}{ext}"
    await asyncio.to_thread(_write_bytes, target, await file.read())
    return {"file_name": file.filename or target.name, "file_path": str(target)}


@router.get("/imports/templates/{template_name}")
async def download_import_template(
    template_name: str,
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
):
    if template_name not in {"users", "schedule"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    templates = {
        "users": [
            "username",
            "full_name",
            "email",
            "phone_number",
            "roles",
            "group_code",
            "логин",
            "фио",
            "почта",
            "телефон",
            "роли",
            "код_группы",
        ],
        "schedule": [
            "group_code",
            "discipline_code",
            "teacher_username",
            "starts_at",
            "ends_at",
            "room",
            "status",
            "код_группы",
            "код_дисциплины",
            "логин_преподавателя",
            "начало",
            "конец",
            "аудитория",
            "статус",
        ],
    }
    columns = templates[template_name]
    template_dir = Path("/tmp/universe-import-templates")
    await asyncio.to_thread(_ensure_directory, template_dir)
    file_path = template_dir / f"{template_name}_template.{format}"
    await asyncio.to_thread(_write_import_template, file_path, format, columns)
    media_type = "text/csv" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)


@router.get("/imports")
async def list_import_jobs(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    rows, total = await _paginate_scalars(
        session,
        select(ImportJob).order_by(ImportJob.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": row.id,
                "job_type": row.job_type.value,
                "status": row.status.value,
                "file_name": row.file_name,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
                "processed_rows": row.processed_rows,
                "total_rows": row.total_rows,
                "error_report": row.error_report,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/imports/{job_id}")
async def get_import_job(
    job_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return {
        "id": row.id,
        "job_type": row.job_type.value,
        "status": row.status.value,
        "file_name": row.file_name,
        "file_path": row.file_path,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
        "processed_rows": row.processed_rows,
        "total_rows": row.total_rows,
        "error_report": row.error_report,
    }


@router.get("/imports/{job_id}/errors/download")
async def download_import_errors(
    job_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    file_path = None
    if row.error_report and isinstance(row.error_report, dict):
        file_path = row.error_report.get("file_path")
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import error report is not available")
    path = Path(str(file_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import error report does not exist")
    return FileResponse(path=path, filename=path.name, media_type="text/csv")


@router.post("/ai-imports")
async def create_ai_import_draft(
    file: UploadFile = File(...),
    mode: AIImportMode = Form(default=AIImportMode.MIXED),
    term_start: date | None = Form(default=None),
    term_end: date | None = Form(default=None),
    first_week_parity: str | None = Form(default=None),
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    wizard = _validate_ai_wizard(
        mode,
        AIImportWizardRequest(
            term_start=term_start,
            term_end=term_end,
            first_week_parity=first_week_parity if first_week_parity in {"odd", "even"} else None,
        ),
    )
    file_name, file_path = await save_ai_import_source(file)
    draft = AIImportDraft(
        created_by=current_user.id,
        mode=mode,
        file_name=file_name,
        file_path=file_path,
        wizard=wizard.model_dump(mode="json"),
        status=AIImportDraftStatus.QUEUED,
    )
    session.add(draft)
    await log_audit(
        session,
        actor_user_id=current_user.id,
        action="ai_import_created",
        entity_type="ai_import_draft",
        entity_id=str(draft.id),
        details={"mode": mode.value, "file_name": file_name},
    )
    await session.commit()
    await session.refresh(draft)
    process_ai_import_draft.delay(str(draft.id))
    return serialize_ai_import_draft(draft)


@router.get("/ai-imports")
async def list_ai_import_drafts(
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    rows, total = await _paginate_scalars(
        session,
        select(AIImportDraft).order_by(AIImportDraft.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": row.id,
                "status": row.status.value,
                "mode": row.mode.value,
                "file_name": row.file_name,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "completed_at": row.completed_at,
                "summary": row.summary,
                "error_report": row.error_report,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/ai-imports/{draft_id}")
async def get_ai_import_draft(
    draft_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    draft = (await session.execute(select(AIImportDraft).where(AIImportDraft.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI import draft not found")
    return serialize_ai_import_draft(draft)


@router.patch("/ai-imports/{draft_id}")
async def patch_ai_import_draft(
    draft_id: UUID,
    payload: AIImportDraftUpdateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
):
    draft = (await session.execute(select(AIImportDraft).where(AIImportDraft.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI import draft not found")
    wizard = _validate_ai_wizard(draft.mode, payload.wizard)
    draft = await update_ai_import_draft_payload(
        session,
        draft=draft,
        wizard=wizard,
        payload_data=payload.payload,
        actor_user_id=current_user.id,
    )
    return serialize_ai_import_draft(draft)


@router.post("/ai-imports/{draft_id}/apply", response_model=ApiMessage)
async def apply_ai_import_draft_endpoint(
    draft_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    draft = (await session.execute(select(AIImportDraft).where(AIImportDraft.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI import draft not found")
    await apply_ai_import_draft(session, draft=draft, actor_user_id=current_user.id)
    return ApiMessage(message="AI import applied")


@router.post("/ai-imports/{draft_id}/reject", response_model=ApiMessage)
async def reject_ai_import_draft_endpoint(
    draft_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    draft = (await session.execute(select(AIImportDraft).where(AIImportDraft.id == draft_id))).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI import draft not found")
    await reject_ai_import_draft(session, draft=draft, actor_user_id=current_user.id)
    return ApiMessage(message="AI import rejected")


@router.post("/exports", response_model=JobResponse)
async def create_export_job(
    payload: ExportJobCreateRequest,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = ExportJob(created_by=current_user.id, **payload.model_dump())
    session.add(job)
    await session.commit()
    await session.refresh(job)
    process_export_job.delay(str(job.id))
    return JobResponse(id=job.id, status=job.status, created_at=job.created_at)


@router.get("/exports")
async def list_export_jobs(
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    rows, total = await _paginate_scalars(
        session,
        select(ExportJob).order_by(ExportJob.created_at.desc()),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [
            {
                "id": row.id,
                "job_type": row.job_type.value,
                "format": row.format.value,
                "status": row.status.value,
                "filters": row.filters,
                "file_path": row.file_path,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/exports/{job_id}")
async def get_export_job(
    job_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(ExportJob).where(ExportJob.id == job_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
    return {
        "id": row.id,
        "job_type": row.job_type.value,
        "format": row.format.value,
        "status": row.status.value,
        "filters": row.filters,
        "file_path": row.file_path,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
    }


@router.get("/exports/{job_id}/download")
async def download_export_file(
    job_id: UUID,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    row = (await session.execute(select(ExportJob).where(ExportJob.id == job_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
    if row.status != JobStatus.DONE or not row.file_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export file is not ready yet")
    file_path = Path(row.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file does not exist")
    return FileResponse(path=file_path, filename=file_path.name, media_type="application/octet-stream")


@router.get("/reports/attendance")
async def attendance_report(
    date_from: date,
    date_to: date,
    student_id: UUID | None = None,
    group_id: UUID | None = None,
    discipline_id: UUID | None = None,
    teacher_id: UUID | None = None,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    if not _is_admin(current_user):
        allowed_group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not allowed_group_ids:
            return {
                "present": 0,
                "late": 0,
                "absent": 0,
                "excused_absent": 0,
                "unexcused_absent": 0,
            }
        if group_id and group_id not in allowed_group_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to group")
        if not group_id:
            # When no group filter set for curator, aggregate by all assigned groups.
            records_stmt = (
                select(AttendanceRecord, Lesson)
                .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
                .where(
                    Lesson.group_id.in_(allowed_group_ids),
                    Lesson.starts_at >= date_from,
                    Lesson.starts_at < _date_end_exclusive(date_to),
                )
            )
            if student_id:
                records_stmt = records_stmt.where(AttendanceRecord.student_id == student_id)
            if discipline_id:
                records_stmt = records_stmt.where(Lesson.discipline_id == discipline_id)
            if teacher_id:
                records_stmt = records_stmt.where(Lesson.teacher_id == teacher_id)
            rows = (await session.execute(records_stmt)).all()
            present = sum(1 for rec, _ in rows if rec.status == AttendanceStatus.PRESENT)
            late = sum(1 for rec, _ in rows if rec.status == AttendanceStatus.LATE)
            absent = sum(1 for rec, _ in rows if rec.status == AttendanceStatus.ABSENT)
            excused_absent = sum(1 for rec, _ in rows if rec.status == AttendanceStatus.ABSENT and rec.is_excused)
            unexcused_absent = sum(1 for rec, _ in rows if rec.status == AttendanceStatus.ABSENT and not rec.is_excused)
            return {
                "present": present,
                "late": late,
                "absent": absent,
                "excused_absent": excused_absent,
                "unexcused_absent": unexcused_absent,
            }

    return await attendance_summary(
        session,
        date_from=date_from,
        date_to=date_to,
        student_id=student_id,
        group_id=group_id,
        discipline_id=discipline_id,
        teacher_id=teacher_id,
    )


@router.get("/reports/lates")
async def lates_report(
    date_from: date,
    date_to: date,
    student_id: UUID | None = None,
    group_id: UUID | None = None,
    discipline_id: UUID | None = None,
    teacher_id: UUID | None = None,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = (
        select(AttendanceRecord, Lesson, User)
        .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
        .join(User, User.id == AttendanceRecord.student_id)
        .where(
            AttendanceRecord.status == AttendanceStatus.LATE,
            Lesson.starts_at >= date_from,
            Lesson.starts_at < _date_end_exclusive(date_to),
        )
    )
    if student_id:
        stmt = stmt.where(AttendanceRecord.student_id == student_id)
    if group_id:
        stmt = stmt.where(Lesson.group_id == group_id)
    if discipline_id:
        stmt = stmt.where(Lesson.discipline_id == discipline_id)
    if teacher_id:
        stmt = stmt.where(Lesson.teacher_id == teacher_id)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stmt = stmt.where(Lesson.group_id.in_(group_ids))
    stmt = stmt.order_by(Lesson.starts_at.desc())
    total = int((await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one())
    rows = (await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    return {
        "items": [
            {
                "attendance_id": attendance.id,
                "lesson_id": lesson.id,
                "student_id": user.id,
                "student_name": user.full_name,
                "marked_at": attendance.marked_at,
                "starts_at": lesson.starts_at,
                "group_id": lesson.group_id,
                "discipline_id": lesson.discipline_id,
                "teacher_id": lesson.teacher_id,
            }
            for attendance, lesson, user in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/reports/absences")
async def absences_report(
    date_from: date,
    date_to: date,
    excused: bool | None = None,
    student_id: UUID | None = None,
    group_id: UUID | None = None,
    discipline_id: UUID | None = None,
    teacher_id: UUID | None = None,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
):
    stmt = (
        select(AttendanceRecord, Lesson, User)
        .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
        .join(User, User.id == AttendanceRecord.student_id)
        .where(
            AttendanceRecord.status == AttendanceStatus.ABSENT,
            Lesson.starts_at >= date_from,
            Lesson.starts_at < _date_end_exclusive(date_to),
        )
    )
    if excused is not None:
        stmt = stmt.where(AttendanceRecord.is_excused == excused)
    if student_id:
        stmt = stmt.where(AttendanceRecord.student_id == student_id)
    if group_id:
        stmt = stmt.where(Lesson.group_id == group_id)
    if discipline_id:
        stmt = stmt.where(Lesson.discipline_id == discipline_id)
    if teacher_id:
        stmt = stmt.where(Lesson.teacher_id == teacher_id)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return {"items": [], "meta": _pagination_meta(page, page_size, 0)}
        stmt = stmt.where(Lesson.group_id.in_(group_ids))
    stmt = stmt.order_by(Lesson.starts_at.desc())
    total = int((await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one())
    rows = (await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    return {
        "items": [
            {
                "attendance_id": attendance.id,
                "lesson_id": lesson.id,
                "student_id": user.id,
                "student_name": user.full_name,
                "is_excused": attendance.is_excused,
                "excused_category": attendance.excused_category,
                "marked_at": attendance.marked_at,
                "starts_at": lesson.starts_at,
                "group_id": lesson.group_id,
                "discipline_id": lesson.discipline_id,
                "teacher_id": lesson.teacher_id,
            }
            for attendance, lesson, user in rows
        ],
        "meta": _pagination_meta(page, page_size, total),
    }


@router.get("/analytics/teachers")
async def teachers_analytics(
    date_from: date,
    date_to: date,
    teacher_id: UUID | None = None,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    from app.db.enums import AttendanceStatus
    from app.db.models import AttendanceRecord

    stmt = (
        select(
            Lesson.teacher_id,
            func.count(AttendanceRecord.id).label("total"),
            func.sum(
                case((AttendanceRecord.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE]), 1), else_=0)
            ).label("attended"),
        )
        .join(AttendanceRecord, AttendanceRecord.lesson_id == Lesson.id)
        .where(Lesson.starts_at >= date_from, Lesson.starts_at < _date_end_exclusive(date_to))
        .group_by(Lesson.teacher_id)
    )
    if teacher_id:
        stmt = stmt.where(Lesson.teacher_id == teacher_id)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return []
        stmt = stmt.where(Lesson.group_id.in_(group_ids))

    rows = (await session.execute(stmt)).all()
    return [
        {
            "teacher_id": row.teacher_id,
            "attendance_pct": round((row.attended or 0) / row.total * 100, 2) if row.total else 0,
            "total_marks": int(row.total or 0),
        }
        for row in rows
    ]


@router.get("/analytics/students")
async def students_analytics(
    date_from: date,
    date_to: date,
    group_id: UUID | None = None,
    discipline_id: UUID | None = None,
    teacher_id: UUID | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    if date_to < date_from:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_to must be greater than date_from")

    allowed_group_ids: list[UUID] | None = None
    if not _is_admin(current_user):
        allowed_group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not allowed_group_ids:
            return {
                "period": {"date_from": date_from, "date_to": date_to},
                "total_students": 0,
                "total_marks": 0,
                "best": [],
                "worst": [],
                "items": [],
            }
        if group_id and group_id not in allowed_group_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to group")

    membership_stmt = (
        select(User, StudentGroupMembership, Group)
        .join(StudentGroupMembership, StudentGroupMembership.student_id == User.id)
        .join(Group, Group.id == StudentGroupMembership.group_id)
        .where(
            StudentGroupMembership.start_date <= date_to,
            or_(
                StudentGroupMembership.end_date.is_(None),
                StudentGroupMembership.end_date >= date_from,
            ),
        )
    )
    if group_id:
        membership_stmt = membership_stmt.where(StudentGroupMembership.group_id == group_id)
    if allowed_group_ids is not None:
        membership_stmt = membership_stmt.where(StudentGroupMembership.group_id.in_(allowed_group_ids))

    membership_rows = (await session.execute(membership_stmt)).all()
    students: dict[UUID, dict[str, Any]] = {}
    for user, membership, group in membership_rows:
        current = students.get(user.id)
        if current and not (membership.is_primary and not current["is_primary"]):
            continue
        students[user.id] = {
            "student_id": user.id,
            "student_name": user.full_name,
            "username": user.username,
            "group_id": group.id,
            "group_code": group.code,
            "group_name": group.name,
            "is_primary": membership.is_primary,
            "present": 0,
            "late": 0,
            "absent": 0,
            "excused_absent": 0,
            "unexcused_absent": 0,
        }

    if not students:
        return {
            "period": {"date_from": date_from, "date_to": date_to},
            "total_students": 0,
            "total_marks": 0,
            "best": [],
            "worst": [],
            "items": [],
        }

    student_ids = list(students)
    attendance_stmt = (
        select(AttendanceRecord, Lesson)
        .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
        .where(
            AttendanceRecord.student_id.in_(student_ids),
            Lesson.starts_at >= date_from,
            Lesson.starts_at < _date_end_exclusive(date_to),
        )
    )
    if group_id:
        attendance_stmt = attendance_stmt.where(Lesson.group_id == group_id)
    if allowed_group_ids is not None:
        attendance_stmt = attendance_stmt.where(Lesson.group_id.in_(allowed_group_ids))
    if discipline_id:
        attendance_stmt = attendance_stmt.where(Lesson.discipline_id == discipline_id)
    if teacher_id:
        attendance_stmt = attendance_stmt.where(Lesson.teacher_id == teacher_id)

    attendance_rows = (await session.execute(attendance_stmt)).all()
    for record, _lesson in attendance_rows:
        bucket = students.get(record.student_id)
        if not bucket:
            continue
        if record.status == AttendanceStatus.PRESENT:
            bucket["present"] += 1
        elif record.status == AttendanceStatus.LATE:
            bucket["late"] += 1
        elif record.status == AttendanceStatus.ABSENT:
            bucket["absent"] += 1
            if record.is_excused:
                bucket["excused_absent"] += 1
            else:
                bucket["unexcused_absent"] += 1

    risk_rows = (
        await session.execute(
            select(RiskCard).where(
                RiskCard.student_id.in_(student_ids),
                RiskCard.is_active.is_(True),
            )
        )
    ).scalars().all()
    risks = {row.student_id: row for row in risk_rows}

    rating_rows = (
        await session.execute(
            select(RatingSnapshot)
            .where(RatingSnapshot.student_id.in_(student_ids))
            .order_by(RatingSnapshot.student_id.asc(), RatingSnapshot.calculated_at.desc())
        )
    ).scalars().all()
    ratings: dict[UUID, RatingSnapshot] = {}
    for row in rating_rows:
        ratings.setdefault(row.student_id, row)

    items: list[dict[str, Any]] = []
    for student_id, row in students.items():
        total = row["present"] + row["late"] + row["absent"]
        attended = row["present"] + row["late"]
        rating = ratings.get(student_id)
        risk = risks.get(student_id)
        rating_score = float(rating.score) if rating else None
        risk_score = float(risk.last_score) if risk else None
        score = _student_period_score(
            total=total,
            present=row["present"],
            late=row["late"],
            absent=row["absent"],
            unexcused_absent=row["unexcused_absent"],
            rating_score=rating_score,
            risk_score=risk_score,
        )
        items.append(
            {
                "student_id": student_id,
                "student_name": row["student_name"],
                "username": row["username"],
                "group_id": row["group_id"],
                "group_code": row["group_code"],
                "group_name": row["group_name"],
                "total_marks": total,
                "present": row["present"],
                "late": row["late"],
                "absent": row["absent"],
                "excused_absent": row["excused_absent"],
                "unexcused_absent": row["unexcused_absent"],
                "attendance_pct": round(attended / total * 100, 2) if total else 0,
                "punctuality_pct": round(row["present"] / total * 100, 2) if total else 0,
                "current_score": score,
                "rating_score": rating_score,
                "risk_score": risk_score,
                "status": _student_analytics_status(
                    score,
                    total=total,
                    late=row["late"],
                    unexcused_absent=row["unexcused_absent"],
                ),
            }
        )

    by_worst = sorted(
        items,
        key=lambda item: (
            item["status"] == "no_data",
            item["current_score"],
            -item["unexcused_absent"],
            -item["late"],
            item["student_name"].casefold(),
        ),
    )
    by_best = sorted(
        [item for item in items if item["status"] != "no_data"],
        key=lambda item: (-item["current_score"], -item["attendance_pct"], item["late"], item["student_name"].casefold()),
    )
    return {
        "period": {"date_from": date_from, "date_to": date_to},
        "total_students": len(items),
        "total_marks": sum(item["total_marks"] for item in items),
        "best": by_best[:limit],
        "worst": by_worst[:limit],
        "items": by_worst,
    }


@router.get("/analytics/teachers/compare")
async def teachers_compare(
    teacher_ids: list[UUID] = Query(default=[]),
    date_from: date | None = None,
    date_to: date | None = None,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    from app.db.enums import AttendanceStatus
    from app.db.models import AttendanceRecord

    stmt = (
        select(
            Lesson.teacher_id,
            func.count(AttendanceRecord.id).label("total"),
            func.sum(
                case(
                    (
                        AttendanceRecord.status.in_(
                            [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("attended"),
            func.sum(case((AttendanceRecord.status == AttendanceStatus.LATE, 1), else_=0)).label("lates"),
            func.sum(case((AttendanceRecord.status == AttendanceStatus.ABSENT, 1), else_=0)).label("absences"),
        )
        .join(AttendanceRecord, AttendanceRecord.lesson_id == Lesson.id)
        .group_by(Lesson.teacher_id)
    )
    if teacher_ids:
        stmt = stmt.where(Lesson.teacher_id.in_(teacher_ids))
    if date_from:
        stmt = stmt.where(Lesson.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Lesson.starts_at < _date_end_exclusive(date_to))
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return []
        stmt = stmt.where(Lesson.group_id.in_(group_ids))
    rows = (await session.execute(stmt)).all()
    return [
        {
            "teacher_id": row.teacher_id,
            "attendance_pct": round((row.attended or 0) / row.total * 100, 2) if row.total else 0,
            "total_marks": int(row.total or 0),
            "lates": int(row.lates or 0),
            "absences": int(row.absences or 0),
        }
        for row in rows
    ]


@router.get("/analytics/teachers/timeseries")
async def teachers_timeseries(
    date_from: date,
    date_to: date,
    granularity: str = Query(default="day", pattern="^(day|week)$"),
    teacher_id: UUID | None = None,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    from app.db.models import AttendanceRecord

    stmt = (
        select(
            Lesson.teacher_id,
            Lesson.starts_at,
            AttendanceRecord.status,
        )
        .join(AttendanceRecord, AttendanceRecord.lesson_id == Lesson.id)
        .where(Lesson.starts_at >= date_from, Lesson.starts_at < _date_end_exclusive(date_to))
    )
    if teacher_id:
        stmt = stmt.where(Lesson.teacher_id == teacher_id)
    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return []
        stmt = stmt.where(Lesson.group_id.in_(group_ids))

    rows = (await session.execute(stmt)).all()
    grouped: dict[tuple[str, str], dict] = {}
    for row_teacher_id, starts_at, attendance_status in rows:
        if granularity == "week":
            iso = starts_at.isocalendar()
            bucket = f"{iso.year}-W{iso.week:02d}"
        else:
            bucket = starts_at.date().isoformat()
        key = (str(row_teacher_id), bucket)
        if key not in grouped:
            grouped[key] = {"teacher_id": str(row_teacher_id), "bucket": bucket, "total": 0, "attended": 0}
        grouped[key]["total"] += 1
        if attendance_status in {AttendanceStatus.PRESENT, AttendanceStatus.LATE}:
            grouped[key]["attended"] += 1

    result = []
    for item in grouped.values():
        total = item["total"]
        attended = item["attended"]
        result.append(
            {
                "teacher_id": item["teacher_id"],
                "bucket": item["bucket"],
                "attendance_pct": round(attended / total * 100, 2) if total else 0,
                "total_marks": total,
                "attended_marks": attended,
            }
        )
    return sorted(result, key=lambda item: (item["teacher_id"], item["bucket"]))


@router.get("/analytics/teachers/{teacher_id}/groups")
async def teacher_groups_analytics(
    teacher_id: UUID,
    date_from: date,
    date_to: date,
    current_user: User = Depends(require_roles(RoleCode.ADMIN, RoleCode.CURATOR)),
    session: AsyncSession = Depends(get_db_session),
):
    from app.db.models import AttendanceRecord

    if not _is_admin(current_user):
        group_ids = await _active_tutor_group_ids(session, current_user.id)
        if not group_ids:
            return []
    else:
        group_ids = None

    stmt = (
        select(
            Lesson.group_id,
            func.count(AttendanceRecord.id).label("total"),
            func.sum(
                case(
                    (
                        AttendanceRecord.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE]),
                        1,
                    ),
                    else_=0,
                )
            ).label("attended"),
            func.sum(case((AttendanceRecord.status == AttendanceStatus.LATE, 1), else_=0)).label("lates"),
            func.sum(case((AttendanceRecord.status == AttendanceStatus.ABSENT, 1), else_=0)).label("absences"),
        )
        .join(AttendanceRecord, AttendanceRecord.lesson_id == Lesson.id)
        .where(
            Lesson.teacher_id == teacher_id,
            Lesson.starts_at >= date_from,
            Lesson.starts_at < _date_end_exclusive(date_to),
        )
        .group_by(Lesson.group_id)
    )
    if group_ids is not None:
        stmt = stmt.where(Lesson.group_id.in_(group_ids))
    rows = (await session.execute(stmt)).all()
    return [
        {
            "teacher_id": str(teacher_id),
            "group_id": row.group_id,
            "attendance_pct": round((row.attended or 0) / row.total * 100, 2) if row.total else 0,
            "total_marks": int(row.total or 0),
            "lates": int(row.lates or 0),
            "absences": int(row.absences or 0),
        }
        for row in rows
    ]
