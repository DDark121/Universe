from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import AttendanceStatus
from app.db.models import AttendanceRecord, Lesson


async def attendance_summary(
    session: AsyncSession,
    date_from: date,
    date_to: date,
    student_id: UUID | None = None,
    group_id: UUID | None = None,
    discipline_id: UUID | None = None,
    teacher_id: UUID | None = None,
) -> dict:
    conditions = [and_(Lesson.starts_at >= date_from, Lesson.starts_at <= date_to)]

    if student_id:
        conditions.append(AttendanceRecord.student_id == student_id)
    if group_id:
        conditions.append(Lesson.group_id == group_id)
    if discipline_id:
        conditions.append(Lesson.discipline_id == discipline_id)
    if teacher_id:
        conditions.append(Lesson.teacher_id == teacher_id)

    stmt = (
        select(
            func.sum(case((AttendanceRecord.status == AttendanceStatus.PRESENT, 1), else_=0)).label("present"),
            func.sum(case((AttendanceRecord.status == AttendanceStatus.LATE, 1), else_=0)).label("late"),
            func.sum(case((AttendanceRecord.status == AttendanceStatus.ABSENT, 1), else_=0)).label("absent"),
            func.sum(
                case(
                    (
                        and_(
                            AttendanceRecord.status == AttendanceStatus.ABSENT,
                            AttendanceRecord.is_excused.is_(True),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("excused_absent"),
            func.sum(
                case(
                    (
                        and_(
                            AttendanceRecord.status == AttendanceStatus.ABSENT,
                            AttendanceRecord.is_excused.is_(False),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("unexcused_absent"),
        )
        .join(Lesson, Lesson.id == AttendanceRecord.lesson_id)
        .where(*conditions)
    )
    row = (await session.execute(stmt)).one()
    return {
        "present": int(row.present or 0),
        "late": int(row.late or 0),
        "absent": int(row.absent or 0),
        "excused_absent": int(row.excused_absent or 0),
        "unexcused_absent": int(row.unexcused_absent or 0),
    }
