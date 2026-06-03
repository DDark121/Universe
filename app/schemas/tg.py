from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.enums import ModerationStatus
from app.schemas.auth import TokenPairResponse


class InviteBindRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    invite_code: str


class BindingRequestCreate(BaseModel):
    telegram_id: int
    telegram_username: str | None = None
    full_name: str | None = None
    requested_user_id: UUID | None = None
    group_code: str | None = None
    note: str | None = None


class TelegramLinkedUserResponse(BaseModel):
    id: UUID
    username: str
    full_name: str
    email: str | None = None
    phone_number: str | None = None
    roles: list[str]
    is_active: bool
    must_change_password: bool


class TelegramBootstrapResponse(BaseModel):
    status: str
    user: TelegramLinkedUserResponse | None = None
    requested_user_id: UUID | None = None
    requested_full_name: str | None = None
    telegram_username: str | None = None
    group_code: str | None = None
    note: str | None = None
    resolved_at: datetime | None = None


class TelegramAuthExchangeRequest(BaseModel):
    telegram_id: int


class TelegramAuthExchangeResponse(TokenPairResponse):
    user: TelegramLinkedUserResponse


class TelegramContextResponse(BaseModel):
    user_id: UUID
    full_name: str
    roles: list[str]


class TelegramStudentFaqItemResponse(BaseModel):
    id: UUID
    category_id: UUID
    category_name: str
    question: str
    answer: str
    keywords: str


class TelegramAssistantReplyRequest(BaseModel):
    telegram_id: int
    message: str


class TelegramAssistantReplyResponse(BaseModel):
    message: str
    used_faq_ids: list[UUID] = Field(default_factory=list)
    status: str


class TelegramButtonAttendanceRequest(BaseModel):
    telegram_id: int
    lesson_id: UUID


class TelegramTeacherQrGenerateRequest(BaseModel):
    telegram_id: int
    lesson_id: UUID


class TelegramTeacherBroadcastRequest(BaseModel):
    telegram_id: int
    group_id: UUID
    message: str


class TelegramTeacherModerationRequest(BaseModel):
    telegram_id: int
    reason_id: UUID
    status: ModerationStatus
    comment: str | None = None


class TelegramLessonActivityScoreRequest(BaseModel):
    telegram_id: int
    lesson_id: UUID
    student_id: UUID
    score: float
    comment: str | None = None
