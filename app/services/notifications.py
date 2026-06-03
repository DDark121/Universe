from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.enums import DeliveryStatus, OutboxStatus
from app.db.models import NotificationDelivery, NotificationOutbox
from app.integrations.tg_client import send_to_tg_service


async def enqueue_notification(
    session: AsyncSession,
    event_type: str,
    payload: dict,
    idempotency_key: str,
    recipient_user_id: UUID | None = None,
    recipient_telegram_id: int | None = None,
) -> NotificationOutbox:
    existing_stmt = select(NotificationOutbox).where(NotificationOutbox.idempotency_key == idempotency_key)
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        return existing

    item = NotificationOutbox(
        event_type=event_type,
        recipient_user_id=recipient_user_id,
        recipient_telegram_id=recipient_telegram_id,
        payload=payload,
        idempotency_key=idempotency_key,
        status=OutboxStatus.PENDING,
    )
    session.add(item)
    await session.flush()
    return item


async def process_outbox_batch(session: AsyncSession, limit: int = 100) -> int:
    stmt = (
        select(NotificationOutbox)
        .where(
            NotificationOutbox.status == OutboxStatus.PENDING,
            (NotificationOutbox.next_attempt_at.is_(None) | (NotificationOutbox.next_attempt_at <= utc_now())),
        )
        .order_by(NotificationOutbox.created_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    processed = 0
    for row in rows:
        ok, provider_response = await send_to_tg_service(
            telegram_id=row.recipient_telegram_id,
            event_type=row.event_type,
            payload=row.payload,
            idempotency_key=row.idempotency_key,
        )

        row.attempts += 1
        if ok:
            row.status = OutboxStatus.SENT
            row.sent_at = utc_now()
            session.add(
                NotificationDelivery(
                    outbox_id=row.id,
                    status=DeliveryStatus.DELIVERED,
                    response_payload=provider_response,
                )
            )
        else:
            row.status = OutboxStatus.PENDING if row.attempts < 5 else OutboxStatus.FAILED
            row.last_error = str(provider_response)
            row.next_attempt_at = utc_now() + timedelta(minutes=min(30, 2 * row.attempts))
            session.add(
                NotificationDelivery(
                    outbox_id=row.id,
                    status=DeliveryStatus.FAILED,
                    error=str(provider_response),
                )
            )
        processed += 1

    await session.commit()
    return processed
