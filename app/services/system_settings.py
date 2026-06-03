from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Discipline, Group, SystemSetting

ATTENDANCE_DEFAULT_WINDOW_START_KEY = "attendance.default_window_start_offset_minutes"
ATTENDANCE_DEFAULT_WINDOW_DURATION_KEY = "attendance.default_window_duration_minutes"
ATTENDANCE_DEFAULT_LATE_THRESHOLD_KEY = "attendance.default_late_threshold_minutes"
ATTENDANCE_BUTTON_ENABLED_KEY = "attendance.button_enabled"
RISK_NOTIFY_TUTOR_KEY = "risk.notify_tutor"


def _setting_scalar(row: SystemSetting | None, default: Any) -> Any:
    if not row:
        return default
    if isinstance(row.value, dict) and "value" in row.value:
        return row.value["value"]
    return row.value


async def get_setting_value(session: AsyncSession, key: str, default: Any = None) -> Any:
    row = (await session.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    return _setting_scalar(row, default)


async def get_settings_map(
    session: AsyncSession,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    rows = (
        await session.execute(select(SystemSetting).where(SystemSetting.key.in_(tuple(defaults.keys()))))
    ).scalars().all()
    mapping = dict(defaults)
    for row in rows:
        mapping[row.key] = _setting_scalar(row, mapping[row.key])
    return mapping


async def get_attendance_defaults(session: AsyncSession) -> dict[str, int]:
    defaults = await get_settings_map(
        session,
        {
            ATTENDANCE_DEFAULT_WINDOW_START_KEY: -5,
            ATTENDANCE_DEFAULT_WINDOW_DURATION_KEY: 20,
            ATTENDANCE_DEFAULT_LATE_THRESHOLD_KEY: 20,
        },
    )
    return {
        "window_start_offset_minutes": int(defaults[ATTENDANCE_DEFAULT_WINDOW_START_KEY]),
        "window_duration_minutes": int(defaults[ATTENDANCE_DEFAULT_WINDOW_DURATION_KEY]),
        "late_threshold_minutes": int(defaults[ATTENDANCE_DEFAULT_LATE_THRESHOLD_KEY]),
    }


def build_lesson_window_config(
    *,
    defaults: dict[str, int],
    group: Group | None = None,
    discipline: Discipline | None = None,
    explicit: dict[str, int | None] | None = None,
) -> dict[str, int]:
    explicit = explicit or {}
    return {
        "window_start_offset_minutes": int(
            explicit.get("window_start_offset_minutes")
            if explicit.get("window_start_offset_minutes") is not None
            else (
                discipline.window_start_offset_override_minutes
                if discipline and discipline.window_start_offset_override_minutes is not None
                else (
                    group.window_start_offset_override_minutes
                    if group and group.window_start_offset_override_minutes is not None
                    else defaults["window_start_offset_minutes"]
                )
            )
        ),
        "window_duration_minutes": int(
            explicit.get("window_duration_minutes")
            if explicit.get("window_duration_minutes") is not None
            else (
                discipline.window_duration_override_minutes
                if discipline and discipline.window_duration_override_minutes is not None
                else (
                    group.window_duration_override_minutes
                    if group and group.window_duration_override_minutes is not None
                    else defaults["window_duration_minutes"]
                )
            )
        ),
        "late_threshold_minutes": int(
            explicit.get("late_threshold_minutes")
            if explicit.get("late_threshold_minutes") is not None
            else (
                discipline.late_threshold_override_minutes
                if discipline and discipline.late_threshold_override_minutes is not None
                else (
                    group.late_threshold_override_minutes
                    if group and group.late_threshold_override_minutes is not None
                    else defaults["late_threshold_minutes"]
                )
            )
        ),
    }


async def resolve_lesson_window_config(
    session: AsyncSession,
    *,
    group_id: UUID | None = None,
    discipline_id: UUID | None = None,
    explicit: dict[str, int | None] | None = None,
) -> dict[str, int]:
    defaults = await get_attendance_defaults(session)

    group = None
    if group_id:
        group = (await session.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()

    discipline = None
    if discipline_id:
        discipline = (
            await session.execute(select(Discipline).where(Discipline.id == discipline_id))
        ).scalar_one_or_none()

    return build_lesson_window_config(
        defaults=defaults,
        group=group,
        discipline=discipline,
        explicit=explicit,
    )
