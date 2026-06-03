from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import AttendanceStatus
from app.db.models import (
    AttendanceRecord,
    Lesson,
    LessonActivityScore,
    RatingConfig,
    RatingSnapshot,
)


async def get_or_create_rating_config(session: AsyncSession) -> RatingConfig:
    stmt = select(RatingConfig).limit(1)
    config = (await session.execute(stmt)).scalar_one_or_none()
    if config:
        return config

    config = RatingConfig(
        attendance_weight=Decimal("50.00"),
        late_weight=Decimal("20.00"),
        unexcused_absence_weight=Decimal("30.00"),
        activity_weight=Decimal("0.00"),
    )
    session.add(config)
    await session.flush()
    return config


async def recalculate_student_rating(
    session: AsyncSession,
    student_id: UUID,
    period_start: date,
    period_end: date,
    group_id: UUID | None = None,
) -> RatingSnapshot:
    config = await get_or_create_rating_config(session)

    stmt = (
        select(AttendanceRecord)
        .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
        .where(
            AttendanceRecord.student_id == student_id,
            and_(Lesson.starts_at >= period_start, Lesson.starts_at <= period_end),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()

    total = len(rows)
    present = len([r for r in rows if r.status == AttendanceStatus.PRESENT])
    late = len([r for r in rows if r.status == AttendanceStatus.LATE])
    unexcused = len([r for r in rows if r.status == AttendanceStatus.ABSENT and not r.is_excused])
    activity_stmt = (
        select(func.avg(LessonActivityScore.score))
        .join(Lesson, Lesson.id == LessonActivityScore.lesson_id)
        .where(
            LessonActivityScore.student_id == student_id,
            and_(Lesson.starts_at >= period_start, Lesson.starts_at <= period_end),
        )
    )
    activity_avg = float((await session.execute(activity_stmt)).scalar_one_or_none() or 0)

    attendance_pct = (present + late) / total * 100 if total else 0

    attendance_component = attendance_pct * float(config.attendance_weight) / 100
    late_component = max(0, 100 - late * 10) * float(config.late_weight) / 100
    unexcused_component = max(0, 100 - unexcused * 25) * float(config.unexcused_absence_weight) / 100
    activity_component = activity_avg * float(config.activity_weight) / 100
    score = max(0, min(100, attendance_component + late_component + unexcused_component + activity_component))

    snapshot = RatingSnapshot(
        student_id=student_id,
        group_id=group_id,
        period_start=period_start,
        period_end=period_end,
        attendance_pct=round(attendance_pct, 2),
        late_count=late,
        unexcused_absence_count=unexcused,
        score=round(score, 2),
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def get_latest_rating(session: AsyncSession, student_id: UUID) -> RatingSnapshot | None:
    stmt = (
        select(RatingSnapshot)
        .where(RatingSnapshot.student_id == student_id)
        .order_by(RatingSnapshot.calculated_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def group_rating_average(session: AsyncSession):
    stmt = select(RatingSnapshot.group_id, func.avg(RatingSnapshot.score)).group_by(RatingSnapshot.group_id)
    return (await session.execute(stmt)).all()
