from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from celery import shared_task
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.enums import ImportJobType, LessonStatus
from app.db.models import (
    AIImportDraft,
    AuditLog,
    ExportJob,
    ImportJob,
    Lesson,
    RatingSnapshot,
    StudentGroupMembership,
    TelegramAccount,
)
from app.services.ai_imports import (
    mark_ai_import_draft_failed,
    mark_ai_import_draft_processing,
    process_ai_import_draft_record,
)
from app.services.attendance import auto_mark_absent_for_lesson
from app.services.escalation import evaluate_student_risk
from app.services.faq_ai import rebuild_faq_index
from app.services.import_export import (
    build_export_path_async,
    build_export_rows,
    export_rows_async,
    mark_import_job_done,
    mark_import_job_failed,
    mark_import_job_processing,
    mark_job_done,
    mark_job_failed,
    mark_job_processing,
    process_import_schedule,
    process_import_users,
)
from app.services.notifications import enqueue_notification, process_outbox_batch
from app.services.rating import recalculate_student_rating
from app.tasks.async_runner import run_async

settings = get_settings()
logger = get_logger(__name__)


def _run_logged_task[T](task_name: str, coro) -> T:
    try:
        return run_async(coro)
    except Exception:
        logger.exception("celery_task_failed", task_name=task_name)
        raise


@shared_task(name="app.tasks.jobs.process_notification_outbox")
def process_notification_outbox() -> int:
    async def _run() -> int:
        async with SessionLocal() as session:
            return await process_outbox_batch(session, limit=200)

    return _run_logged_task("process_notification_outbox", _run())


@shared_task(name="app.tasks.jobs.auto_mark_absences")
def auto_mark_absences() -> int:
    async def _run() -> int:
        async with SessionLocal() as session:
            stmt = select(Lesson).where(
                Lesson.starts_at <= utc_now(),
                Lesson.status.in_([LessonStatus.PLANNED, LessonStatus.IN_PROGRESS, LessonStatus.COMPLETED]),
            )
            lessons = (await session.execute(stmt)).scalars().all()
            total = 0
            for lesson in lessons:
                total += await auto_mark_absent_for_lesson(session, lesson.id)
            return total

    return _run_logged_task("auto_mark_absences", _run())


@shared_task(name="app.tasks.jobs.recalculate_ratings")
def recalculate_ratings() -> int:
    async def _run() -> int:
        async with SessionLocal() as session:
            period_end = utc_now().date()
            period_start = period_end - timedelta(days=30)

            stmt = select(StudentGroupMembership.student_id, StudentGroupMembership.group_id).where(
                StudentGroupMembership.end_date.is_(None)
            )
            pairs = (await session.execute(stmt)).all()

            count = 0
            for student_id, group_id in pairs:
                await recalculate_student_rating(
                    session,
                    student_id=student_id,
                    group_id=group_id,
                    period_start=period_start,
                    period_end=period_end,
                )
                count += 1
            return count

    return _run_logged_task("recalculate_ratings", _run())


@shared_task(name="app.tasks.jobs.evaluate_escalations")
def evaluate_escalations() -> int:
    async def _run() -> int:
        async with SessionLocal() as session:
            stmt = select(RatingSnapshot.student_id).distinct()
            student_ids = [row[0] for row in (await session.execute(stmt)).all()]
            count = 0
            for student_id in student_ids:
                event = await evaluate_student_risk(session, student_id)
                if event:
                    count += 1
            return count

    return _run_logged_task("evaluate_escalations", _run())


@shared_task(name="app.tasks.jobs.cleanup_audit_logs")
def cleanup_audit_logs() -> int:
    async def _run() -> int:
        cutoff = utc_now() - timedelta(days=settings.audit_retention_months * 30)
        async with SessionLocal() as session:
            stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
            result = await session.execute(stmt)
            await session.commit()
            return int(result.rowcount or 0)

    return _run_logged_task("cleanup_audit_logs", _run())


@shared_task(name="app.tasks.jobs.process_attendance_window_notifications")
def process_attendance_window_notifications() -> int:
    async def _run() -> int:
        now = utc_now()
        async with SessionLocal() as session:
            stmt = select(Lesson).where(
                Lesson.starts_at <= now + timedelta(hours=2),
                Lesson.ends_at >= now - timedelta(hours=2),
                Lesson.status.in_([LessonStatus.PLANNED, LessonStatus.IN_PROGRESS]),
            )
            lessons = (await session.execute(stmt)).scalars().all()
            sent = 0
            for lesson in lessons:
                window_start = lesson.starts_at + timedelta(minutes=lesson.window_start_offset_minutes)
                window_end = window_start + timedelta(minutes=lesson.window_duration_minutes)
                event_type = None
                if window_start <= now <= window_start + timedelta(minutes=1):
                    event_type = "attendance_window_open"
                elif (window_end - timedelta(minutes=3)) <= now <= (window_end - timedelta(minutes=2)):
                    event_type = "attendance_window_close_soon"
                if not event_type:
                    continue

                members = (
                    await session.execute(
                        select(StudentGroupMembership.student_id).where(
                            StudentGroupMembership.group_id == lesson.group_id,
                            StudentGroupMembership.end_date.is_(None),
                        )
                    )
                ).all()
                minute_bucket = now.strftime("%Y%m%d%H%M")
                for (student_id,) in members:
                    telegram_id = (
                        await session.execute(
                            select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == student_id)
                        )
                    ).scalar_one_or_none()
                    await enqueue_notification(
                        session,
                        event_type=event_type,
                        recipient_user_id=student_id,
                        recipient_telegram_id=telegram_id,
                        payload={
                            "lesson_id": str(lesson.id),
                            "group_id": str(lesson.group_id),
                            "window_start": window_start.isoformat(),
                            "window_end": window_end.isoformat(),
                        },
                        idempotency_key=f"{event_type}:{lesson.id}:{student_id}:{minute_bucket}",
                    )
                    sent += 1
            await session.commit()
            return sent

    return _run_logged_task("process_attendance_window_notifications", _run())


@shared_task(name="app.tasks.jobs.process_faq_index_rebuild")
def process_faq_index_rebuild() -> str:
    async def _run() -> str:
        result = await rebuild_faq_index()
        return str(result.get("status", "unknown"))

    return _run_logged_task("process_faq_index_rebuild", _run())


@shared_task(name="app.tasks.jobs.process_export_job")
def process_export_job(job_id: str) -> None:
    async def _run() -> None:
        async with SessionLocal() as session:
            try:
                job_uuid = UUID(job_id)
            except ValueError:
                return
            job = (
                await session.execute(select(ExportJob).where(ExportJob.id == job_uuid))
            ).scalar_one_or_none()
            if not job:
                return

            await mark_job_processing(session, job)
            try:
                rows = await build_export_rows(session, job)
                out = await build_export_path_async(job.id, job.format)
                await export_rows_async(out, job.format, rows)
                await mark_job_done(session, job, str(out))
            except Exception:
                await mark_job_failed(session, job)

    _run_logged_task("process_export_job", _run())


@shared_task(name="app.tasks.jobs.process_import_job")
def process_import_job(job_id: str) -> None:
    async def _run() -> None:
        async with SessionLocal() as session:
            try:
                job_uuid = UUID(job_id)
            except ValueError:
                return
            job = (
                await session.execute(select(ImportJob).where(ImportJob.id == job_uuid))
            ).scalar_one_or_none()
            if not job:
                return
            await mark_import_job_processing(session, job)
            try:
                if job.job_type == ImportJobType.USERS:
                    result = await process_import_users(session, job)
                else:
                    result = await process_import_schedule(session, job)
                await mark_import_job_done(session, job, result)
            except Exception as exc:  # noqa: BLE001
                await mark_import_job_failed(session, job, str(exc))

    _run_logged_task("process_import_job", _run())


@shared_task(name="app.tasks.jobs.process_ai_import_draft")
def process_ai_import_draft(draft_id: str) -> None:
    async def _run() -> None:
        async with SessionLocal() as session:
            try:
                draft_uuid = UUID(draft_id)
            except ValueError:
                return
            draft = (
                await session.execute(select(AIImportDraft).where(AIImportDraft.id == draft_uuid))
            ).scalar_one_or_none()
            if not draft:
                return
            await mark_ai_import_draft_processing(session, draft)
            try:
                await process_ai_import_draft_record(session, draft)
            except Exception as exc:  # noqa: BLE001
                await mark_ai_import_draft_failed(session, draft, str(exc))

    _run_logged_task("process_ai_import_draft", _run())
