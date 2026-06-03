from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import EscalationStatus
from app.db.models import (
    EscalationEvent,
    EscalationRule,
    RatingSnapshot,
    RiskCard,
    RiskForecast,
    StudentGroupMembership,
    TelegramAccount,
    TutorGroupAssignment,
)
from app.services.notifications import enqueue_notification
from app.services.rating import get_latest_rating
from app.services.system_settings import RISK_NOTIFY_TUTOR_KEY, get_setting_value


async def refresh_risk_forecasts(session: AsyncSession, student_id: UUID) -> list[RiskForecast]:
    snapshots = (
        await session.execute(
            select(RatingSnapshot)
            .where(RatingSnapshot.student_id == student_id)
            .order_by(RatingSnapshot.calculated_at.desc())
            .limit(6)
        )
    ).scalars().all()
    if not snapshots:
        return []

    latest = snapshots[0]
    oldest = snapshots[-1]
    day_span = max(1, (latest.period_end - oldest.period_start).days)
    score_delta = float(latest.score) - float(oldest.score)
    late_delta = latest.late_count - oldest.late_count
    unexcused_delta = latest.unexcused_absence_count - oldest.unexcused_absence_count

    score_trend_per_day = score_delta / day_span
    late_trend_per_day = late_delta / day_span
    unexcused_trend_per_day = unexcused_delta / day_span

    results: list[RiskForecast] = []
    for horizon in (14, 28):
        predicted_score = max(0.0, min(100.0, float(latest.score) + score_trend_per_day * horizon))
        predicted_lates = max(0, int(round(latest.late_count + late_trend_per_day * horizon)))
        predicted_unexcused = max(
            0,
            int(round(latest.unexcused_absence_count + unexcused_trend_per_day * horizon)),
        )
        existing = (
            await session.execute(
                select(RiskForecast).where(
                    RiskForecast.student_id == student_id,
                    RiskForecast.horizon_days == horizon,
                    RiskForecast.calculated_for_date == latest.period_end,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.predicted_score = round(predicted_score, 2)
            existing.predicted_late_count = predicted_lates
            existing.predicted_unexcused_absence_count = predicted_unexcused
            existing.confidence = min(95, 50 + len(snapshots) * 8)
            existing.explain = {
                "horizon_days": horizon,
                "base_score": float(latest.score),
                "score_trend_per_day": round(score_trend_per_day, 3),
                "late_trend_per_day": round(late_trend_per_day, 3),
                "unexcused_trend_per_day": round(unexcused_trend_per_day, 3),
                "source_snapshots": len(snapshots),
            }
            results.append(existing)
            continue

        item = RiskForecast(
            student_id=student_id,
            horizon_days=horizon,
            period_days=30,
            predicted_score=round(predicted_score, 2),
            predicted_late_count=predicted_lates,
            predicted_unexcused_absence_count=predicted_unexcused,
            confidence=min(95, 50 + len(snapshots) * 8),
            explain={
                "horizon_days": horizon,
                "base_score": float(latest.score),
                "score_trend_per_day": round(score_trend_per_day, 3),
                "late_trend_per_day": round(late_trend_per_day, 3),
                "unexcused_trend_per_day": round(unexcused_trend_per_day, 3),
                "source_snapshots": len(snapshots),
            },
            calculated_for_date=latest.period_end,
        )
        session.add(item)
        results.append(item)

    return results


async def evaluate_student_risk(session: AsyncSession, student_id: UUID) -> EscalationEvent | None:
    rule_stmt = select(EscalationRule).where(EscalationRule.is_active.is_(True)).order_by(EscalationRule.created_at.asc()).limit(1)
    rule = (await session.execute(rule_stmt)).scalar_one_or_none()
    if not rule:
        return None

    latest = await get_latest_rating(session, student_id)
    if not latest:
        return None

    await refresh_risk_forecasts(session, student_id)

    triggered = (
        latest.unexcused_absence_count >= rule.threshold_unexcused_absences
        or latest.late_count >= rule.threshold_lates
        or float(latest.score) < rule.min_rating
    )

    if not triggered:
        return None

    existing_stmt = select(EscalationEvent).where(
        EscalationEvent.student_id == student_id,
        EscalationEvent.status == EscalationStatus.OPEN,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        return existing

    event = EscalationEvent(
        student_id=student_id,
        rule_id=rule.id,
        status=EscalationStatus.OPEN,
        reason_payload={
            "late_count": latest.late_count,
            "unexcused_absence_count": latest.unexcused_absence_count,
            "score": float(latest.score),
        },
    )
    session.add(event)

    risk_stmt = select(RiskCard).where(RiskCard.student_id == student_id, RiskCard.is_active.is_(True))
    risk_card = (await session.execute(risk_stmt)).scalar_one_or_none()
    reasons = {
        "late_count": latest.late_count,
        "unexcused_absence_count": latest.unexcused_absence_count,
        "score": float(latest.score),
    }
    if risk_card:
        risk_card.reasons = reasons
        risk_card.last_score = latest.score
        risk_card.late_count = latest.late_count
        risk_card.unexcused_absence_count = latest.unexcused_absence_count
    else:
        session.add(
            RiskCard(
                student_id=student_id,
                is_active=True,
                last_score=latest.score,
                late_count=latest.late_count,
                unexcused_absence_count=latest.unexcused_absence_count,
                reasons=reasons,
            )
        )

    await enqueue_notification(
        session,
        event_type="risk_warning",
        recipient_user_id=student_id,
        payload={
            "event": "risk_warning",
            "reason": reasons,
            "explain": "Сработал порог дисциплинарного риска по опозданиям/пропускам/рейтингу.",
        },
        idempotency_key=f"risk_warning:{student_id}:{event.id}",
    )

    if bool(await get_setting_value(session, RISK_NOTIFY_TUTOR_KEY, True)):
        memberships = (
            await session.execute(
                select(StudentGroupMembership.group_id).where(
                    StudentGroupMembership.student_id == student_id,
                    or_(
                        StudentGroupMembership.end_date.is_(None),
                        StudentGroupMembership.end_date >= latest.period_end,
                    ),
                )
            )
        ).all()
        group_ids = [group_id for (group_id,) in memberships]
        if group_ids:
            tutor_rows = (
                await session.execute(
                    select(TutorGroupAssignment.tutor_user_id, TutorGroupAssignment.group_id)
                    .where(
                        TutorGroupAssignment.group_id.in_(group_ids),
                        TutorGroupAssignment.is_active.is_(True),
                    )
                )
            ).all()
            for tutor_user_id, group_id in tutor_rows:
                tutor_telegram_id = (
                    await session.execute(
                        select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == tutor_user_id)
                    )
                ).scalar_one_or_none()
                await enqueue_notification(
                    session,
                    event_type="tutor_risk_warning",
                    recipient_user_id=tutor_user_id,
                    recipient_telegram_id=tutor_telegram_id,
                    payload={
                        "student_id": str(student_id),
                        "group_id": str(group_id),
                        "score": float(latest.score),
                        "late_count": latest.late_count,
                        "unexcused_absence_count": latest.unexcused_absence_count,
                    },
                    idempotency_key=f"tutor_risk_warning:{event.id}:{tutor_user_id}:{group_id}",
                )

    await session.commit()
    await session.refresh(event)
    return event
