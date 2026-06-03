from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

settings = get_settings()


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_university_tz(value: datetime) -> datetime:
    return value.astimezone(ZoneInfo(settings.app_timezone))
