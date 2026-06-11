from enum import StrEnum


class RoleCode(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    CURATOR = "curator"


class BindingRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LessonStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELED = "canceled"
    RESCHEDULED = "rescheduled"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"


class AttendanceSource(StrEnum):
    QR = "qr"
    BUTTON = "button"
    TEACHER_MANUAL = "teacher_manual"
    AUTO_ABSENCE = "auto_absence"
    BIOMETRIC = "biometric"


class AbsenceReasonType(StrEnum):
    ILLNESS = "illness"
    ACADEMIC = "academic"
    PERSONAL = "personal"
    OTHER = "other"


class ModerationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class BroadcastScope(StrEnum):
    GROUP = "group"
    FILTER = "filter"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class EscalationStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ImportJobType(StrEnum):
    USERS = "users"
    SCHEDULE = "schedule"


class AIImportMode(StrEnum):
    MIXED = "mixed"
    USERS = "users"
    SCHEDULE = "schedule"


class AIImportDraftStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DRAFT = "draft"
    APPLIED = "applied"
    FAILED = "failed"
    REJECTED = "rejected"


class ExportJobType(StrEnum):
    REPORT = "report"
    RISK_LIST = "risk_list"
    SCHEDULE = "schedule"


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
