from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BiometricAttendanceRequest(BaseModel):
    fingerprint_hash: str = Field(min_length=16, max_length=255)
    lesson_id: UUID | None = None
    context_token: str | None = None
    scanner_event_id: str = Field(min_length=1, max_length=128)


class BiometricAttendanceResponse(BaseModel):
    success: bool
    reason: str | None = None
    attendance_id: UUID | None = None
    student_id: UUID | None = None
    lesson_id: UUID | None = None
    status: str | None = None
    marked_at: datetime | None = None


class ClientErrorReportRequest(BaseModel):
    app: Literal["student-app", "web-admin"]
    level: Literal["error", "warning"] = "error"
    message: str = Field(min_length=1, max_length=2_000)
    stack: str | None = Field(default=None, max_length=8_000)
    url: str = Field(min_length=1, max_length=2_000)
    user_agent: str = Field(min_length=1, max_length=1_000)
    correlation_id: str | None = Field(default=None, max_length=128)
    release: str | None = Field(default=None, max_length=128)
    context: dict[str, Any] | None = None
