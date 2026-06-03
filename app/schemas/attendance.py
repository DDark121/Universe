from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.db.enums import AbsenceReasonType, AttendanceStatus, ModerationStatus


class QRGenerateRequest(BaseModel):
    lesson_id: UUID


class QRGenerateResponse(BaseModel):
    token: str
    deeplink: str
    expires_at: datetime


class AttendanceMarkRequest(BaseModel):
    telegram_id: int
    qr_token: str


class StudentQRMarkRequest(BaseModel):
    qr_token: str


class DynamicQRSessionStartRequest(BaseModel):
    lesson_id: UUID


class DynamicQRSessionStartResponse(BaseModel):
    session_id: UUID
    ws_url: str
    session_expires_at: datetime


class AttendanceManualCorrectionRequest(BaseModel):
    lesson_id: UUID
    student_id: UUID
    status: AttendanceStatus
    reason: str


class AttendanceRecordResponse(BaseModel):
    lesson_id: UUID
    student_id: UUID
    status: AttendanceStatus
    marked_at: datetime
    is_excused: bool


class AbsenceReasonCreateRequest(BaseModel):
    lesson_id: UUID
    reason_type: AbsenceReasonType
    comment: str | None = None
    is_predeclared: bool = False


class AbsenceModerationRequest(BaseModel):
    reason_id: UUID
    status: ModerationStatus
    comment: str | None = None
