from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.db.enums import (
    ExportFormat,
    ExportJobType,
    ImportJobType,
    JobStatus,
    LessonStatus,
    RoleCode,
)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = None
    phone_number: str = Field(min_length=7, max_length=32)
    full_name: str = Field(min_length=2, max_length=255)
    roles: list[RoleCode]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("phone_number is required")
        return normalized


class UserUpdateRequest(BaseModel):
    email: str | None = None
    phone_number: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_archived: bool | None = None

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @field_validator("phone_number")
    @classmethod
    def normalize_optional_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class GroupCreateRequest(BaseModel):
    code: str
    name: str
    faculty_id: UUID | None = None
    stream_id: UUID | None = None
    parent_group_id: UUID | None = None
    is_subgroup: bool = False
    window_start_offset_override_minutes: int | None = None
    window_duration_override_minutes: int | None = None
    late_threshold_override_minutes: int | None = None
    telegram_chat_id: int | None = None
    telegram_chat_title: str | None = None


class GroupUpdateRequest(BaseModel):
    code: str | None = None
    name: str | None = None
    faculty_id: UUID | None = None
    stream_id: UUID | None = None
    parent_group_id: UUID | None = None
    is_subgroup: bool | None = None
    is_archived: bool | None = None
    window_start_offset_override_minutes: int | None = None
    window_duration_override_minutes: int | None = None
    late_threshold_override_minutes: int | None = None
    telegram_chat_id: int | None = None
    telegram_chat_title: str | None = None
    telegram_chat_is_active: bool | None = None


class FacultyCreateRequest(BaseModel):
    code: str
    name: str


class FacultyUpdateRequest(BaseModel):
    code: str | None = None
    name: str | None = None
    is_archived: bool | None = None


class StreamCreateRequest(BaseModel):
    faculty_id: UUID
    name: str


class StreamUpdateRequest(BaseModel):
    faculty_id: UUID | None = None
    name: str | None = None
    is_archived: bool | None = None


class DisciplineCreateRequest(BaseModel):
    code: str
    name: str
    window_start_offset_override_minutes: int | None = None
    window_duration_override_minutes: int | None = None
    late_threshold_override_minutes: int | None = None


class DisciplineUpdateRequest(BaseModel):
    code: str | None = None
    name: str | None = None
    is_archived: bool | None = None
    window_start_offset_override_minutes: int | None = None
    window_duration_override_minutes: int | None = None
    late_threshold_override_minutes: int | None = None


class AssignmentCreateRequest(BaseModel):
    teacher_id: UUID
    discipline_id: UUID
    group_id: UUID


class AssignmentUpdateRequest(BaseModel):
    teacher_id: UUID | None = None
    discipline_id: UUID | None = None
    group_id: UUID | None = None
    is_active: bool | None = None


class TutorAssignmentCreateRequest(BaseModel):
    tutor_user_id: UUID
    group_id: UUID


class TutorAssignmentUpdateRequest(BaseModel):
    is_active: bool | None = None


class LessonCreateRequest(BaseModel):
    group_id: UUID
    discipline_id: UUID
    teacher_id: UUID
    starts_at: datetime
    ends_at: datetime
    room: str | None = None
    status: LessonStatus = LessonStatus.PLANNED
    window_start_offset_minutes: int | None = None
    window_duration_minutes: int | None = None
    late_threshold_minutes: int | None = None


class LessonUpdateRequest(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    room: str | None = None
    status: LessonStatus | None = None
    canceled_reason: str | None = None
    window_start_offset_minutes: int | None = None
    window_duration_minutes: int | None = None
    late_threshold_minutes: int | None = None


class LessonStatusUpdateRequest(BaseModel):
    status: LessonStatus
    canceled_reason: str | None = None
    rescheduled_from_id: UUID | None = None


class InviteCodeCreateRequest(BaseModel):
    role_code: RoleCode
    expires_at: datetime
    max_activations: int = Field(ge=1, le=1000)
    group_id: UUID | None = None
    discipline_id: UUID | None = None


class InviteCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    max_activations: int


class BindingDecisionRequest(BaseModel):
    request_id: UUID
    user_id: UUID
    approve: bool


class UserRolesUpdateRequest(BaseModel):
    roles: list[RoleCode]


class SystemSettingRequest(BaseModel):
    value: dict


class FaqCategoryCreateRequest(BaseModel):
    name: str
    sort_order: int = 100


class FaqCategoryUpdateRequest(BaseModel):
    name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class FaqItemCreateRequest(BaseModel):
    category_id: UUID
    question: str
    answer: str
    keywords: str = ""


class FaqItemUpdateRequest(BaseModel):
    category_id: UUID | None = None
    question: str | None = None
    answer: str | None = None
    keywords: str | None = None
    is_active: bool | None = None


class RatingConfigRequest(BaseModel):
    attendance_weight: float
    late_weight: float
    unexcused_absence_weight: float
    activity_weight: float


class EscalationRuleRequest(BaseModel):
    name: str
    threshold_unexcused_absences: int
    threshold_lates: int
    min_rating: int
    is_active: bool = True


class EscalationRuleUpdateRequest(BaseModel):
    name: str | None = None
    threshold_unexcused_absences: int | None = None
    threshold_lates: int | None = None
    min_rating: int | None = None
    is_active: bool | None = None


class ImportJobCreateRequest(BaseModel):
    job_type: ImportJobType
    file_name: str
    file_path: str


class ExportJobCreateRequest(BaseModel):
    job_type: ExportJobType
    format: ExportFormat
    filters: dict | None = None


class JobResponse(BaseModel):
    id: UUID
    status: JobStatus
    created_at: datetime


class StudentTransferRequest(BaseModel):
    student_id: UUID
    target_group_id: UUID
    transfer_date: date


class TutorBroadcastRequest(BaseModel):
    group_id: UUID
    message: str = Field(min_length=1, max_length=4000)


class BiometricDeviceCreateRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=128)
    secret: str = Field(min_length=8, max_length=256)
    description: str | None = None
    allowed_ips: list[str] = Field(default_factory=list)
    is_active: bool = True


class BiometricDeviceUpdateRequest(BaseModel):
    description: str | None = None
    allowed_ips: list[str] | None = None
    is_active: bool | None = None
    secret: str | None = Field(default=None, min_length=8, max_length=256)


class StudentBiometricCreateRequest(BaseModel):
    student_id: UUID
    fingerprint_hash: str = Field(min_length=16, max_length=255)
    is_active: bool = True


class StudentBiometricUpdateRequest(BaseModel):
    is_active: bool | None = None


class LessonActivityScoreRequest(BaseModel):
    lesson_id: UUID
    student_id: UUID
    score: float
    comment: str | None = None
