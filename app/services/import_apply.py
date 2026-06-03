from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import generate_temp_password, hash_password
from app.core.time import utc_now
from app.db.enums import LessonStatus, RoleCode
from app.db.models import (
    Discipline,
    Faculty,
    Group,
    Lesson,
    Role,
    Stream,
    StudentGroupMembership,
    TeacherAssignment,
    User,
)
from app.services.system_settings import build_lesson_window_config, get_attendance_defaults

EntityAction = Literal["match_existing", "create_new", "upsert"]
RoleUpdateStrategy = Literal["merge", "replace"]


async def load_roles_by_codes(session: AsyncSession, codes: Iterable[RoleCode]) -> list[Role]:
    codes = list(dict.fromkeys(codes))
    rows = (await session.execute(select(Role).where(Role.code.in_(codes)))).scalars().all()
    if len(rows) != len(codes):
        raise ValueError("Some role codes are not configured")
    return rows


async def resolve_faculty(
    session: AsyncSession,
    *,
    code: str | None,
    name: str | None,
    action: EntityAction = "match_existing",
    existing_id: UUID | None = None,
) -> Faculty:
    row = None
    if existing_id:
        row = (await session.execute(select(Faculty).where(Faculty.id == existing_id))).scalar_one_or_none()
    if not row and code:
        row = (await session.execute(select(Faculty).where(Faculty.code == code))).scalar_one_or_none()
    if not row and name:
        row = (
            await session.execute(select(Faculty).where(func.lower(Faculty.name) == name.lower()))
        ).scalar_one_or_none()

    if action == "match_existing":
        if not row:
            raise ValueError("Faculty mapping is unresolved")
        if code and not row.code:
            row.code = code
        if name:
            row.name = name
        return row

    if action == "upsert":
        if row:
            if code:
                row.code = code
            if name:
                row.name = name
            return row
        if not code or not name:
            raise ValueError("Faculty code/name are required")
        row = Faculty(code=code, name=name)
        session.add(row)
        await session.flush()
        return row

    if row:
        raise ValueError("Faculty already exists, switch mapping to match_existing")
    if not code or not name:
        raise ValueError("Faculty code/name are required")
    row = Faculty(code=code, name=name)
    session.add(row)
    await session.flush()
    return row


async def resolve_stream(
    session: AsyncSession,
    *,
    name: str | None,
    faculty_id: UUID | None,
    action: EntityAction = "match_existing",
    existing_id: UUID | None = None,
) -> Stream:
    row = None
    if existing_id:
        row = (await session.execute(select(Stream).where(Stream.id == existing_id))).scalar_one_or_none()
    if not row and name and faculty_id:
        row = (
            await session.execute(
                select(Stream).where(
                    Stream.faculty_id == faculty_id,
                    func.lower(Stream.name) == name.lower(),
                )
            )
        ).scalar_one_or_none()

    if action == "match_existing":
        if not row:
            raise ValueError("Stream mapping is unresolved")
        if name:
            row.name = name
        if faculty_id:
            row.faculty_id = faculty_id
        return row

    if action == "upsert":
        if row:
            if name:
                row.name = name
            if faculty_id:
                row.faculty_id = faculty_id
            return row
        if not name or faculty_id is None:
            raise ValueError("Stream name/faculty are required")
        row = Stream(name=name, faculty_id=faculty_id)
        session.add(row)
        await session.flush()
        return row

    if row:
        raise ValueError("Stream already exists, switch mapping to match_existing")
    if not name or faculty_id is None:
        raise ValueError("Stream name/faculty are required")
    row = Stream(name=name, faculty_id=faculty_id)
    session.add(row)
    await session.flush()
    return row


async def resolve_group(
    session: AsyncSession,
    *,
    code: str | None,
    name: str | None,
    faculty_id: UUID | None = None,
    stream_id: UUID | None = None,
    parent_group_id: UUID | None = None,
    is_subgroup: bool = False,
    action: EntityAction = "match_existing",
    existing_id: UUID | None = None,
) -> Group:
    row = None
    if existing_id:
        row = (await session.execute(select(Group).where(Group.id == existing_id))).scalar_one_or_none()
    if not row and code:
        row = (await session.execute(select(Group).where(Group.code == code))).scalar_one_or_none()

    if action == "match_existing":
        if not row:
            raise ValueError("Group mapping is unresolved")
        if code:
            row.code = code
        if name:
            row.name = name
        row.faculty_id = faculty_id
        row.stream_id = stream_id
        row.parent_group_id = parent_group_id
        row.is_subgroup = is_subgroup
        return row

    if action == "upsert":
        if row:
            if code:
                row.code = code
            if name:
                row.name = name
            row.faculty_id = faculty_id
            row.stream_id = stream_id
            row.parent_group_id = parent_group_id
            row.is_subgroup = is_subgroup
            return row
        if not code or not name:
            raise ValueError("Group code/name are required")
        row = Group(
            code=code,
            name=name,
            faculty_id=faculty_id,
            stream_id=stream_id,
            parent_group_id=parent_group_id,
            is_subgroup=is_subgroup,
        )
        session.add(row)
        await session.flush()
        return row

    if row:
        raise ValueError("Group already exists, switch mapping to match_existing")
    if not code or not name:
        raise ValueError("Group code/name are required")
    row = Group(
        code=code,
        name=name,
        faculty_id=faculty_id,
        stream_id=stream_id,
        parent_group_id=parent_group_id,
        is_subgroup=is_subgroup,
    )
    session.add(row)
    await session.flush()
    return row


async def resolve_discipline(
    session: AsyncSession,
    *,
    code: str | None,
    name: str | None,
    action: EntityAction = "match_existing",
    existing_id: UUID | None = None,
) -> Discipline:
    row = None
    if existing_id:
        row = (await session.execute(select(Discipline).where(Discipline.id == existing_id))).scalar_one_or_none()
    if not row and code:
        row = (await session.execute(select(Discipline).where(Discipline.code == code))).scalar_one_or_none()
    if not row and name:
        row = (
            await session.execute(select(Discipline).where(func.lower(Discipline.name) == name.lower()))
        ).scalar_one_or_none()

    if action == "match_existing":
        if not row:
            raise ValueError("Discipline mapping is unresolved")
        if code:
            row.code = code
        if name:
            row.name = name
        return row

    if action == "upsert":
        if row:
            if code:
                row.code = code
            if name:
                row.name = name
            return row
        if not code or not name:
            raise ValueError("Discipline code/name are required")
        row = Discipline(code=code, name=name)
        session.add(row)
        await session.flush()
        return row

    if row:
        raise ValueError("Discipline already exists, switch mapping to match_existing")
    if not code or not name:
        raise ValueError("Discipline code/name are required")
    row = Discipline(code=code, name=name)
    session.add(row)
    await session.flush()
    return row


async def resolve_user(
    session: AsyncSession,
    *,
    username: str | None,
    full_name: str | None,
    email: str | None,
    role_codes: list[RoleCode],
    phone_number: str | None = None,
    action: EntityAction = "match_existing",
    existing_id: UUID | None = None,
    role_update_strategy: RoleUpdateStrategy = "merge",
) -> User:
    row = None
    if existing_id:
        row = (
            await session.execute(select(User).where(User.id == existing_id).options(selectinload(User.roles)))
        ).scalar_one_or_none()
    if not row and username:
        row = (
            await session.execute(select(User).where(User.username == username).options(selectinload(User.roles)))
        ).scalar_one_or_none()
    if not row and email:
        row = (
            await session.execute(select(User).where(User.email == email).options(selectinload(User.roles)))
        ).scalar_one_or_none()
    if not row and phone_number:
        row = (
            await session.execute(select(User).where(User.phone_number == phone_number).options(selectinload(User.roles)))
        ).scalar_one_or_none()
    if not row and full_name:
        rows = (
            await session.execute(
                select(User)
                .where(func.lower(User.full_name) == full_name.lower())
                .options(selectinload(User.roles))
            )
        ).scalars().all()
        if len(rows) == 1:
            row = rows[0]

    if action == "match_existing":
        if not row:
            raise ValueError("User mapping is unresolved")
    elif action == "create_new":
        if row:
            raise ValueError("User already exists, switch mapping to match_existing")
        if not username or not full_name:
            raise ValueError("User username/full_name are required")
        roles = await load_roles_by_codes(session, role_codes)
        row = User(
            username=username,
            full_name=full_name,
            email=email,
            phone_number=phone_number,
            password_hash=hash_password(generate_temp_password()),
            must_change_password=True,
            is_active=True,
            roles=roles,
        )
        session.add(row)
        await session.flush()
        return row
    else:
        if not row:
            if not username or not full_name:
                raise ValueError("User username/full_name are required")
            roles = await load_roles_by_codes(session, role_codes)
            row = User(
                username=username,
                full_name=full_name,
                email=email,
                phone_number=phone_number,
                password_hash=hash_password(generate_temp_password()),
                must_change_password=True,
                is_active=True,
                roles=roles,
            )
            session.add(row)
            await session.flush()
            return row

    if username and action == "upsert":
        row.username = username
    if full_name:
        row.full_name = full_name
    if email and (row.email is None or row.email == email):
        row.email = email
    if phone_number and (row.phone_number is None or row.phone_number == phone_number):
        row.phone_number = phone_number
    roles = await load_roles_by_codes(session, role_codes)
    if role_update_strategy == "replace":
        row.roles = roles
    else:
        merged = {role.code: role for role in row.roles}
        for role in roles:
            merged[role.code] = role
        row.roles = list(merged.values())
    return row


async def ensure_student_membership(
    session: AsyncSession,
    *,
    student_id: UUID,
    group_id: UUID,
    start_date: date | None = None,
) -> StudentGroupMembership:
    membership = (
        await session.execute(
            select(StudentGroupMembership).where(
                StudentGroupMembership.student_id == student_id,
                StudentGroupMembership.group_id == group_id,
                or_(StudentGroupMembership.end_date.is_(None), StudentGroupMembership.end_date >= utc_now().date()),
            )
        )
    ).scalar_one_or_none()
    if membership:
        return membership

    membership = StudentGroupMembership(
        student_id=student_id,
        group_id=group_id,
        start_date=start_date or utc_now().date(),
        end_date=None,
        is_primary=True,
    )
    session.add(membership)
    await session.flush()
    return membership


async def ensure_teacher_assignment(
    session: AsyncSession,
    *,
    teacher_id: UUID,
    discipline_id: UUID,
    group_id: UUID,
) -> TeacherAssignment:
    row = (
        await session.execute(
            select(TeacherAssignment).where(
                TeacherAssignment.teacher_id == teacher_id,
                TeacherAssignment.discipline_id == discipline_id,
                TeacherAssignment.group_id == group_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.is_active = True
        return row

    row = TeacherAssignment(
        teacher_id=teacher_id,
        discipline_id=discipline_id,
        group_id=group_id,
        is_active=True,
    )
    session.add(row)
    await session.flush()
    return row


async def _load_lesson_defaults(session: AsyncSession) -> dict[str, int]:
    values = await get_attendance_defaults(session)
    return {
        "window_start": values["window_start_offset_minutes"],
        "window_duration": values["window_duration_minutes"],
        "late_threshold": values["late_threshold_minutes"],
    }


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def upsert_lesson(
    session: AsyncSession,
    *,
    group: Group,
    discipline: Discipline,
    teacher: User,
    starts_at: datetime,
    ends_at: datetime,
    room: str | None,
    status: LessonStatus = LessonStatus.PLANNED,
) -> Lesson:
    starts_at = _as_utc(starts_at)
    ends_at = _as_utc(ends_at)
    if ends_at <= starts_at:
        raise ValueError("Lesson end must be greater than start")

    row = (
        await session.execute(
            select(Lesson).where(
                Lesson.group_id == group.id,
                Lesson.discipline_id == discipline.id,
                Lesson.teacher_id == teacher.id,
                Lesson.starts_at == starts_at,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.ends_at = ends_at
        row.room = room
        row.status = status
        return row

    defaults = await _load_lesson_defaults(session)
    lesson_window = build_lesson_window_config(
        defaults={
            "window_start_offset_minutes": defaults["window_start"],
            "window_duration_minutes": defaults["window_duration"],
            "late_threshold_minutes": defaults["late_threshold"],
        },
        group=group,
        discipline=discipline,
    )
    row = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=starts_at,
        ends_at=ends_at,
        room=room,
        status=status,
        **lesson_window,
    )
    session.add(row)
    await session.flush()
    return row
