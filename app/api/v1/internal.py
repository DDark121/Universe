from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_service_token
from app.core.cache import get_redis_client
from app.core.db import get_db_session
from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.enums import DeliveryStatus, OutboxStatus
from app.db.models import NotificationDelivery, NotificationOutbox
from app.schemas.common import HealthResponse
from app.tasks.jobs import (
    auto_mark_absences,
    cleanup_audit_logs,
    evaluate_escalations,
    process_attendance_window_notifications,
    process_notification_outbox,
    recalculate_ratings,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=utc_now())


@router.get("/ready", response_model=HealthResponse)
async def ready(session: AsyncSession = Depends(get_db_session)) -> HealthResponse:
    await session.execute(text("select 1"))
    redis = get_redis_client()
    await redis.ping()
    return HealthResponse(status="ready", timestamp=utc_now())


@router.post("/delivery/callback")
async def delivery_callback(
    outbox_id: str,
    delivered: bool,
    external_id: str | None = None,
    error: str | None = None,
    _: dict = Depends(verify_service_token),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        outbox_uuid = UUID(outbox_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid outbox_id") from exc

    row = (
        await session.execute(select(NotificationOutbox).where(NotificationOutbox.id == outbox_uuid))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Outbox item not found")

    row.status = OutboxStatus.SENT if delivered else OutboxStatus.FAILED
    if delivered:
        row.sent_at = utc_now()
    else:
        row.last_error = error

    session.add(
        NotificationDelivery(
            outbox_id=row.id,
            status=DeliveryStatus.DELIVERED if delivered else DeliveryStatus.FAILED,
            external_id=external_id,
            error=error,
            response_payload={"received_at": datetime.now().isoformat()},
        )
    )
    await session.commit()
    return {"message": "updated"}


@router.post("/jobs/trigger/{job_name}")
async def trigger_job(job_name: str, _: dict = Depends(verify_service_token)):
    jobs = {
        "process_notification_outbox": process_notification_outbox,
        "auto_mark_absences": auto_mark_absences,
        "process_attendance_window_notifications": process_attendance_window_notifications,
        "recalculate_ratings": recalculate_ratings,
        "evaluate_escalations": evaluate_escalations,
        "cleanup_audit_logs": cleanup_audit_logs,
    }
    fn = jobs.get(job_name)
    if not fn:
        raise HTTPException(status_code=404, detail="Unknown job")
    result = fn.delay()
    return {"task_id": result.id}
