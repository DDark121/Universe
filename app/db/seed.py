from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.db.enums import RoleCode
from app.db.models import (
    EscalationRule,
    NotificationTemplate,
    RatingConfig,
    Role,
    SystemSetting,
    User,
    UserRole,
)

DEFAULT_TEMPLATES = {
    "attendance_window_open": "Окно отметки открыто.",
    "attendance_window_close_soon": "Скоро закрытие окна отметки.",
    "attendance_late_detected": "Зафиксировано опоздание на занятие.",
    "absence_reason_requested": "Вы пропустили занятие. Укажите причину отсутствия.",
    "reason_moderation_result": "Результат модерации причины обновлен.",
    "lesson_rescheduled": "Занятие перенесено.",
    "lesson_canceled": "Занятие отменено.",
    "risk_warning": "Внимание: вы находитесь в зоне риска.",
    "tutor_risk_warning": "У студента вашей группы сработал риск-порог.",
    "tutor_broadcast": "Сообщение от тьютора.",
    "teacher_broadcast": "Сообщение от преподавателя.",
}


async def _ensure_roles(session):
    for role_code in RoleCode:
        stmt = select(Role).where(Role.code == role_code)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            display_name = "Тьютор" if role_code == RoleCode.CURATOR else role_code.value.capitalize()
            session.add(Role(code=role_code, name=display_name))


async def _ensure_admin(session):
    stmt = select(User).where(User.username == "admin")
    admin = (await session.execute(stmt)).scalar_one_or_none()
    if admin:
        return

    admin = User(
        username="admin",
        full_name="System Administrator",
        email="admin@example.local",
        phone_number="+70000000000",
        password_hash=hash_password("Admin123!"),
        must_change_password=True,
        is_active=True,
    )
    session.add(admin)
    await session.flush()

    role_stmt = select(Role).where(Role.code == RoleCode.ADMIN)
    admin_role = (await session.execute(role_stmt)).scalar_one()
    session.add(UserRole(user_id=admin.id, role_id=admin_role.id))


async def _ensure_templates(session):
    for code, body in DEFAULT_TEMPLATES.items():
        stmt = select(NotificationTemplate).where(NotificationTemplate.code == code)
        if (await session.execute(stmt)).scalar_one_or_none():
            continue
        session.add(NotificationTemplate(code=code, title=None, body=body, is_active=True))


async def _ensure_rating(session):
    stmt = select(RatingConfig).limit(1)
    if (await session.execute(stmt)).scalar_one_or_none():
        return
    session.add(
        RatingConfig(
            attendance_weight=Decimal("50.00"),
            late_weight=Decimal("20.00"),
            unexcused_absence_weight=Decimal("30.00"),
            activity_weight=Decimal("0.00"),
        )
    )


async def _ensure_escalation_rule(session):
    stmt = select(EscalationRule).where(EscalationRule.name == "default-moderate")
    if (await session.execute(stmt)).scalar_one_or_none():
        return

    session.add(
        EscalationRule(
            name="default-moderate",
            threshold_unexcused_absences=3,
            threshold_lates=4,
            min_rating=60,
            is_active=True,
        )
    )


async def _ensure_default_settings(session):
    defaults = {
        "attendance.default_window_start_offset_minutes": {"value": -5},
        "attendance.default_window_duration_minutes": {"value": 20},
        "attendance.default_late_threshold_minutes": {"value": 20},
        "attendance.button_enabled": {"value": True},
        "attendance.teacher_correction_window_days": {"value": 3},
        "attendance.qr_dynamic_slot_seconds": {"value": 3},
        "attendance.qr_dynamic_grace_slots": {"value": 2},
        "security.audit_retention_months": {"value": 24},
        "security.biometric.max_timestamp_drift_seconds": {"value": 30},
        "security.biometric.nonce_ttl_seconds": {"value": 90},
        "localization.language": {"value": "ru"},
        "auth.2fa.optional": {"value": True},
        "tutor.broadcast.max_message_len": {"value": 2000},
        "risk.notify_tutor": {"value": True},
    }
    for key, value in defaults.items():
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        if (await session.execute(stmt)).scalar_one_or_none():
            continue
        session.add(SystemSetting(key=key, value=value))


async def seed_initial_data() -> None:
    async with SessionLocal() as session:
        try:
            await _ensure_roles(session)
            await _ensure_admin(session)
            await _ensure_templates(session)
            await _ensure_rating(session)
            await _ensure_escalation_rule(session)
            await _ensure_default_settings(session)
            await session.commit()
        except (SQLAlchemyError, OSError):
            # Migrations, database DNS, or the database itself might still be settling on container boot.
            await session.rollback()


if __name__ == "__main__":
    asyncio.run(seed_initial_data())
