from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.time import utc_now
from app.db.enums import AttendanceSource, AttendanceStatus, LessonStatus
from app.db.models import AttendanceRecord, Discipline, Group, Lesson, User
from app.services.rating import recalculate_student_rating


@pytest.mark.asyncio
async def test_recalculate_student_rating_creates_snapshot(session):
    teacher = User(username="teacher_r", full_name="Teacher", password_hash="x", must_change_password=False)
    student = User(username="student_r", full_name="Student", password_hash="x", must_change_password=False)
    group = Group(code="RG-1", name="Rating Group")
    discipline = Discipline(code="RD-1", name="Rating Discipline")
    session.add_all([teacher, student, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(days=1),
        ends_at=now - timedelta(days=1, hours=-1),
        status=LessonStatus.COMPLETED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )

    session.add(lesson)
    await session.flush()

    session.add(
        AttendanceRecord(
            lesson_id=lesson.id,
            student_id=student.id,
            status=AttendanceStatus.PRESENT,
            source=AttendanceSource.QR,
            marked_at=lesson.starts_at,
        )
    )
    await session.commit()

    snapshot = await recalculate_student_rating(
        session,
        student_id=student.id,
        group_id=group.id,
        period_start=(now - timedelta(days=30)).date(),
        period_end=now.date(),
    )

    assert float(snapshot.score) >= 0
    assert float(snapshot.attendance_pct) == 100.0
