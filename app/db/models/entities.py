from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.db.enums import (
    AbsenceReasonType,
    AIImportDraftStatus,
    AIImportMode,
    AttendanceSource,
    AttendanceStatus,
    BindingRequestStatus,
    BroadcastScope,
    DeliveryStatus,
    EscalationStatus,
    ExportFormat,
    ExportJobType,
    ImportJobType,
    JobStatus,
    LessonStatus,
    ModerationStatus,
    OutboxStatus,
    RoleCode,
)


class Role(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "roles"

    code: Mapped[RoleCode] = mapped_column(Enum(RoleCode, name="role_code"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles",
        lazy="selectin",
        backref="users",
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshSession(Base, UUIDMixin):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramAccount(Base, UUIDMixin):
    __tablename__ = "telegram_accounts"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Faculty(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "faculties"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Stream(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "streams"

    faculty_id: Mapped[UUID] = mapped_column(ForeignKey("faculties.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Group(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "groups"

    faculty_id: Mapped[UUID | None] = mapped_column(ForeignKey("faculties.id", ondelete="SET NULL"))
    stream_id: Mapped[UUID | None] = mapped_column(ForeignKey("streams.id", ondelete="SET NULL"))
    parent_group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_subgroup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    window_start_offset_override_minutes: Mapped[int | None] = mapped_column(Integer)
    window_duration_override_minutes: Mapped[int | None] = mapped_column(Integer)
    late_threshold_override_minutes: Mapped[int | None] = mapped_column(Integer)


class Discipline(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "disciplines"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    window_start_offset_override_minutes: Mapped[int | None] = mapped_column(Integer)
    window_duration_override_minutes: Mapped[int | None] = mapped_column(Integer)
    late_threshold_override_minutes: Mapped[int | None] = mapped_column(Integer)


class GroupTelegramChat(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "group_telegram_chats"

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StudentGroupMembership(Base, UUIDMixin):
    __tablename__ = "student_group_memberships"

    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_membership_student_active", "student_id", "end_date"),
    )


class TeacherAssignment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "teacher_assignments"

    teacher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    discipline_id: Mapped[UUID] = mapped_column(ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("teacher_id", "discipline_id", "group_id", name="uq_teacher_assignment"),
    )


class TutorGroupAssignment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tutor_group_assignments"

    tutor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tutor_user_id", "group_id", name="uq_tutor_group_assignment"),
        Index("ix_tutor_group_assignment_tutor_active", "tutor_user_id", "is_active"),
    )


class Lesson(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "lessons"

    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    discipline_id: Mapped[UUID] = mapped_column(ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=False)
    teacher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    room: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[LessonStatus] = mapped_column(
        Enum(LessonStatus, name="lesson_status"),
        default=LessonStatus.PLANNED,
        nullable=False,
    )
    window_start_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    window_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    late_threshold_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    canceled_reason: Mapped[str | None] = mapped_column(Text)
    rescheduled_from_id: Mapped[UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"))

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="lesson_valid_interval"),
    )


class InviteCode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role_code: Mapped[RoleCode] = mapped_column(Enum(RoleCode, name="invite_role_code"), nullable=False)
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    discipline_id: Mapped[UUID | None] = mapped_column(ForeignKey("disciplines.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_activations: Mapped[int] = mapped_column(Integer, nullable=False)
    activation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class InviteActivation(Base, UUIDMixin):
    __tablename__ = "invite_activations"

    invite_code_id: Mapped[UUID] = mapped_column(ForeignKey("invite_codes.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramBindingRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "telegram_binding_requests"

    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    group_code: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    requested_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[BindingRequestStatus] = mapped_column(
        Enum(BindingRequestStatus, name="binding_request_status"),
        default=BindingRequestStatus.PENDING,
        nullable=False,
    )
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QRToken(Base, UUIDMixin):
    __tablename__ = "qr_tokens"

    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_qr_lesson_active", "lesson_id", "is_active"),)


class QRSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "qr_sessions"

    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    teacher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_slot_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_qr_sessions_lesson_active", "lesson_id", "is_active"),
        Index("ix_qr_sessions_teacher_active", "teacher_id", "is_active"),
    )


class AttendanceRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "attendance_records"

    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, name="attendance_status"),
        nullable=False,
    )
    source: Mapped[AttendanceSource] = mapped_column(
        Enum(AttendanceSource, name="attendance_source"),
        nullable=False,
    )
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    marked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    correction_reason: Mapped[str | None] = mapped_column(Text)
    is_excused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    excused_category: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id", name="uq_attendance_lesson_student"),
        Index("ix_attendance_student_marked_at", "student_id", "marked_at"),
    )


class LessonActivityScore(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "lesson_activity_scores"

    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    comment: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id", name="uq_activity_score_lesson_student"),
        Index("ix_activity_score_student", "student_id"),
    )


class AbsenceReason(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "absence_reasons"

    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reason_type: Mapped[AbsenceReasonType] = mapped_column(
        Enum(AbsenceReasonType, name="absence_reason_type"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text)
    is_predeclared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    moderation_status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, name="moderation_status"),
        default=ModerationStatus.PENDING,
        nullable=False,
    )
    moderated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    moderation_comment: Mapped[str | None] = mapped_column(Text)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AbsenceAttachment(Base, UUIDMixin):
    __tablename__ = "absence_attachments"

    reason_id: Mapped[UUID] = mapped_column(ForeignKey("absence_reasons.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notification_templates"

    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationOutbox(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notification_outbox"

    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recipient_telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status"),
        default=OutboxStatus.PENDING,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class NotificationDelivery(Base, UUIDMixin):
    __tablename__ = "notification_deliveries"

    outbox_id: Mapped[UUID] = mapped_column(
        ForeignKey("notification_outbox.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status"),
        default=DeliveryStatus.PENDING,
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    response_payload: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Broadcast(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "broadcasts"

    sender_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[BroadcastScope] = mapped_column(
        Enum(BroadcastScope, name="broadcast_scope"),
        nullable=False,
    )
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    filters: Mapped[dict | None] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(Text, nullable=False)


class BroadcastRecipient(Base, UUIDMixin):
    __tablename__ = "broadcast_recipients"

    broadcast_id: Mapped[UUID] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="broadcast_recipient_status"),
        default=DeliveryStatus.PENDING,
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RatingConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "rating_configs"

    attendance_weight: Mapped[float] = mapped_column(Numeric(5, 2), default=50, nullable=False)
    late_weight: Mapped[float] = mapped_column(Numeric(5, 2), default=20, nullable=False)
    unexcused_absence_weight: Mapped[float] = mapped_column(Numeric(5, 2), default=30, nullable=False)
    activity_weight: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RatingSnapshot(Base, UUIDMixin):
    __tablename__ = "rating_snapshots"

    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    attendance_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    late_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unexcused_absence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EscalationRule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "escalation_rules"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    threshold_unexcused_absences: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold_lates: Mapped[int] = mapped_column(Integer, nullable=False)
    min_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EscalationEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "escalation_events"

    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("escalation_rules.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[EscalationStatus] = mapped_column(
        Enum(EscalationStatus, name="escalation_status"),
        default=EscalationStatus.OPEN,
        nullable=False,
    )
    reason_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskCard(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "risk_cards"

    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    unexcused_absence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    late_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "is_active", name="uq_risk_card_student_active"),
    )


class RiskForecast(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "risk_forecasts"

    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    predicted_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    predicted_late_count: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_unexcused_absence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=70)
    explain: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    calculated_for_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index("ix_risk_forecasts_student_date", "student_id", "calculated_for_date"),
        Index("ix_risk_forecasts_horizon", "horizon_days", "calculated_for_date"),
    )


class FaqCategory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "faq_categories"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FaqItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "faq_items"

    category_id: Mapped[UUID] = mapped_column(ForeignKey("faq_categories.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(String(1024), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class LoginAudit(Base, UUIDMixin):
    __tablename__ = "login_audit"

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BiometricDevice(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "biometric_devices"

    device_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_ips: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class StudentBiometric(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "student_biometrics"

    student_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_student_biometrics_student_active", "student_id", "is_active"),
    )


class BiometricEvent(Base, UUIDMixin):
    __tablename__ = "biometric_events"

    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scanner_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lesson_id: Mapped[UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"))
    student_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    fingerprint_hash: Mapped[str | None] = mapped_column(String(255))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        UniqueConstraint("device_id", "scanner_event_id", name="uq_biometric_device_scanner_event"),
        Index("ix_biometric_events_student_created", "student_id", "created_at"),
    )


class ImportJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "import_jobs"

    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[ImportJobType] = mapped_column(Enum(ImportJobType, name="import_job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="import_job_status"),
        default=JobStatus.PENDING,
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_report: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIImportDraft(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ai_import_drafts"

    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[AIImportDraftStatus] = mapped_column(
        Enum(AIImportDraftStatus, name="ai_import_draft_status"),
        default=AIImportDraftStatus.QUEUED,
        nullable=False,
    )
    mode: Mapped[AIImportMode] = mapped_column(Enum(AIImportMode, name="ai_import_mode"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    wizard: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSON)
    payload: Mapped[dict | None] = mapped_column(JSON)
    issues: Mapped[list[dict] | None] = mapped_column(JSON)
    apply_result: Mapped[dict | None] = mapped_column(JSON)
    error_report: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_ai_import_drafts_status_created", "status", "created_at"),
    )


class ExportJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "export_jobs"

    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[ExportJobType] = mapped_column(Enum(ExportJobType, name="export_job_type"), nullable=False)
    format: Mapped[ExportFormat] = mapped_column(Enum(ExportFormat, name="export_format"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="export_job_status"),
        default=JobStatus.PENDING,
        nullable=False,
    )
    filters: Mapped[dict | None] = mapped_column(JSON)
    file_path: Mapped[str | None] = mapped_column(String(512))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SystemSetting(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
