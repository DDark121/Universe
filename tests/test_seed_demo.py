from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db.models import (
    AttendanceRecord,
    Group,
    GroupTelegramChat,
    Lesson,
    RatingSnapshot,
    StudentGroupMembership,
    TeacherAssignment,
    TutorGroupAssignment,
)
from app.db.seed import (
    _ensure_default_settings,
    _ensure_demo_group_16422,
    _ensure_escalation_rule,
    _ensure_rating,
    _ensure_roles,
)


@pytest.mark.asyncio
async def test_seed_creates_demo_group_16422_with_schedule_attendance_and_tutor(session):
    await _ensure_roles(session)
    await _ensure_rating(session)
    await _ensure_escalation_rule(session)
    await _ensure_default_settings(session)
    await _ensure_demo_group_16422(session)
    await session.commit()

    group = (await session.execute(select(Group).where(Group.code == "164.22"))).scalar_one()
    assert group.name == "164.22"

    student_count = (
        await session.execute(
            select(func.count()).select_from(StudentGroupMembership).where(StudentGroupMembership.group_id == group.id)
        )
    ).scalar_one()
    assert student_count == 8

    june_week_lessons = (
        await session.execute(
            select(func.count())
            .select_from(Lesson)
            .where(
                Lesson.group_id == group.id,
                Lesson.starts_at >= datetime(2026, 6, 8, tzinfo=UTC),
                Lesson.starts_at < datetime(2026, 6, 13, tzinfo=UTC),
            )
        )
    ).scalar_one()
    assert june_week_lessons == 15

    assignment_count = (
        await session.execute(
            select(func.count()).select_from(TeacherAssignment).where(TeacherAssignment.group_id == group.id)
        )
    ).scalar_one()
    assert assignment_count == 8

    assert (
        await session.execute(
            select(TutorGroupAssignment).where(
                TutorGroupAssignment.group_id == group.id,
                TutorGroupAssignment.is_active.is_(True),
            )
        )
    ).scalar_one()

    assert (
        await session.execute(
            select(GroupTelegramChat).where(
                GroupTelegramChat.group_id == group.id,
                GroupTelegramChat.telegram_chat_id == -100164220001,
            )
        )
    ).scalar_one()

    attendance_count = (
        await session.execute(
            select(func.count())
            .select_from(AttendanceRecord)
            .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
            .where(Lesson.group_id == group.id)
        )
    ).scalar_one()
    assert attendance_count == 480

    rating_count = (await session.execute(select(func.count()).select_from(RatingSnapshot))).scalar_one()
    assert rating_count == 8
