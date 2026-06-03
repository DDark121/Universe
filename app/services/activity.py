from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, LessonActivityScore
from app.services.audit import log_audit


async def upsert_lesson_activity_score(
    session: AsyncSession,
    *,
    teacher_id: UUID,
    lesson_id: UUID,
    student_id: UUID,
    score: float,
    comment: str | None = None,
) -> LessonActivityScore:
    lesson = (
        await session.execute(select(Lesson).where(Lesson.id == lesson_id, Lesson.teacher_id == teacher_id))
    ).scalar_one_or_none()
    if not lesson:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")

    row = (
        await session.execute(
            select(LessonActivityScore).where(
                LessonActivityScore.lesson_id == lesson_id,
                LessonActivityScore.student_id == student_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.score = score
        row.comment = comment
        row.recorded_by = teacher_id
    else:
        row = LessonActivityScore(
            lesson_id=lesson_id,
            student_id=student_id,
            score=score,
            comment=comment,
            recorded_by=teacher_id,
        )
        session.add(row)
        await session.flush()

    await log_audit(
        session,
        actor_user_id=teacher_id,
        action="lesson.activity_score_upsert",
        entity_type="lesson_activity_score",
        entity_id=str(row.id),
        details={
            "lesson_id": str(lesson_id),
            "student_id": str(student_id),
            "score": score,
        },
    )
    await session.commit()
    await session.refresh(row)
    return row
