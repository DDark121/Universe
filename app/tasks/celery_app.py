from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "universe_backend",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.jobs"],
)

celery_app.conf.update(
    timezone=settings.app_timezone,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "process-notification-outbox": {
            "task": "app.tasks.jobs.process_notification_outbox",
            "schedule": 30.0,
        },
        "auto-mark-absent": {
            "task": "app.tasks.jobs.auto_mark_absences",
            "schedule": 60.0,
        },
        "attendance-window-notifications": {
            "task": "app.tasks.jobs.process_attendance_window_notifications",
            "schedule": 30.0,
        },
        "recalculate-ratings": {
            "task": "app.tasks.jobs.recalculate_ratings",
            "schedule": 300.0,
        },
        "evaluate-escalations": {
            "task": "app.tasks.jobs.evaluate_escalations",
            "schedule": 300.0,
        },
        "cleanup-audit": {
            "task": "app.tasks.jobs.cleanup_audit_logs",
            "schedule": 86400.0,
        },
    },
)
