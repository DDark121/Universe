from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.time import utc_now
from app.db.enums import AttendanceSource, AttendanceStatus, LessonStatus, RoleCode
from app.db.models import (
    AttendanceRecord,
    Discipline,
    Group,
    Lesson,
    Role,
    StudentGroupMembership,
    TelegramAccount,
    User,
)
from app.services.attendance import (
    auto_mark_absent_for_lesson,
    build_dynamic_qr_token,
    create_dynamic_qr_session,
    generate_qr_token,
    mark_attendance_by_biometric,
    mark_attendance_by_qr,
)


@pytest.mark.asyncio
async def test_qr_mark_attendance(session):
    role_student = Role(code=RoleCode.STUDENT, name="Student")
    role_teacher = Role(code=RoleCode.TEACHER, name="Teacher")
    teacher = User(
        username="teacher_1",
        full_name="Teacher One",
        password_hash="x",
        must_change_password=False,
    )
    student = User(
        username="student_1",
        full_name="Student One",
        password_hash="x",
        must_change_password=False,
    )
    teacher.roles.append(role_teacher)
    student.roles.append(role_student)

    group = Group(code="G-1", name="Group 1")
    discipline = Discipline(code="D-1", name="Math")
    session.add_all([role_student, role_teacher, teacher, student, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=89),
        status=LessonStatus.PLANNED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )

    membership = StudentGroupMembership(
        student_id=student.id,
        group_id=group.id,
        start_date=now.date() - timedelta(days=1),
        end_date=None,
        is_primary=True,
    )
    tg_account = TelegramAccount(user_id=student.id, telegram_id=100500, username="st")

    session.add_all([lesson, membership, tg_account])
    await session.commit()

    raw_token, _ = await generate_qr_token(session, lesson_id=lesson.id, teacher_id=teacher.id)
    record = await mark_attendance_by_qr(session, telegram_id=100500, qr_token=raw_token)

    assert record.status in {AttendanceStatus.PRESENT, AttendanceStatus.LATE}
    assert record.source == AttendanceSource.QR

    with pytest.raises(HTTPException) as exc:
        await mark_attendance_by_qr(session, telegram_id=100500, qr_token=raw_token)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_auto_absence_marks_only_unmarked_students(session):
    role_student = Role(code=RoleCode.STUDENT, name="Student")
    teacher = User(username="teacher2", full_name="Teacher", password_hash="x", must_change_password=False)
    student_a = User(username="st_a", full_name="A", password_hash="x", must_change_password=False)
    student_b = User(username="st_b", full_name="B", password_hash="x", must_change_password=False)
    student_a.roles.append(role_student)
    student_b.roles.append(role_student)

    group = Group(code="G-2", name="Group 2")
    discipline = Discipline(code="D-2", name="Physics")
    session.add_all([role_student, teacher, student_a, student_b, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        status=LessonStatus.COMPLETED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )

    session.add(lesson)
    await session.flush()

    session.add_all(
        [
            StudentGroupMembership(
                student_id=student_a.id,
                group_id=group.id,
                start_date=(now - timedelta(days=1)).date(),
                end_date=None,
                is_primary=True,
            ),
            StudentGroupMembership(
                student_id=student_b.id,
                group_id=group.id,
                start_date=(now - timedelta(days=1)).date(),
                end_date=None,
                is_primary=True,
            ),
            AttendanceRecord(
                lesson_id=lesson.id,
                student_id=student_a.id,
                status=AttendanceStatus.PRESENT,
                source=AttendanceSource.QR,
                marked_at=lesson.starts_at,
            ),
        ]
    )
    await session.commit()

    created = await auto_mark_absent_for_lesson(session, lesson.id)
    assert created == 1


@pytest.mark.asyncio
async def test_dynamic_qr_mark_attendance(session):
    role_student = Role(code=RoleCode.STUDENT, name="Student")
    role_teacher = Role(code=RoleCode.TEACHER, name="Teacher")
    teacher = User(
        username="teacher_ws",
        full_name="Teacher WS",
        password_hash="x",
        must_change_password=False,
    )
    student = User(
        username="student_ws",
        full_name="Student WS",
        password_hash="x",
        must_change_password=False,
    )
    teacher.roles.append(role_teacher)
    student.roles.append(role_student)

    group = Group(code="G-WS", name="Group WS")
    discipline = Discipline(code="D-WS", name="Physics")
    session.add_all([role_student, role_teacher, teacher, student, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=89),
        status=LessonStatus.PLANNED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )

    membership = StudentGroupMembership(
        student_id=student.id,
        group_id=group.id,
        start_date=now.date() - timedelta(days=1),
        end_date=None,
        is_primary=True,
    )
    tg_account = TelegramAccount(user_id=student.id, telegram_id=120500, username="st_ws")

    session.add_all([lesson, membership, tg_account])
    await session.commit()

    qr_session = await create_dynamic_qr_session(session, lesson_id=lesson.id, teacher_id=teacher.id)
    token, _slot = build_dynamic_qr_token(qr_session)
    record = await mark_attendance_by_qr(session, telegram_id=120500, qr_token=token)
    assert record.source == AttendanceSource.QR


@pytest.mark.asyncio
async def test_biometric_mark_attendance(session):
    role_student = Role(code=RoleCode.STUDENT, name="Student")
    teacher = User(
        username="teacher_bio",
        full_name="Teacher Bio",
        password_hash="x",
        must_change_password=False,
    )
    student = User(
        username="student_bio",
        full_name="Student Bio",
        password_hash="x",
        must_change_password=False,
    )
    student.roles.append(role_student)
    group = Group(code="G-BIO", name="Group BIO")
    discipline = Discipline(code="D-BIO", name="Biology")
    session.add_all([role_student, teacher, student, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=89),
        status=LessonStatus.PLANNED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )
    session.add(lesson)
    await session.flush()
    session.add(
        StudentGroupMembership(
            student_id=student.id,
            group_id=group.id,
            start_date=(now - timedelta(days=1)).date(),
            end_date=None,
            is_primary=True,
        )
    )
    await session.commit()

    record = await mark_attendance_by_biometric(session, student_id=student.id, lesson_id=lesson.id)
    assert record.source == AttendanceSource.BIOMETRIC
