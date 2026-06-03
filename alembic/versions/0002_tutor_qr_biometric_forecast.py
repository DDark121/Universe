"""tutor assignments, dynamic qr, biometric api and risk forecasts

Revision ID: 0002_tutor_qr_biometric_forecast
Revises: 0001_initial
Create Date: 2026-02-23 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_tutor_qr_biometric_forecast"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE attendance_source ADD VALUE IF NOT EXISTS 'biometric'")

    if _column_exists(inspector, "faculties", "is_archived") is False:
        op.add_column(
            "faculties",
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.alter_column("faculties", "is_archived", server_default=None)

    if _column_exists(inspector, "streams", "is_archived") is False:
        op.add_column(
            "streams",
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.alter_column("streams", "is_archived", server_default=None)

    if _table_exists(inspector, "tutor_group_assignments") is False:
        op.create_table(
            "tutor_group_assignments",
            sa.Column("tutor_user_id", sa.Uuid(), nullable=False),
            sa.Column("group_id", sa.Uuid(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tutor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tutor_user_id", "group_id", name="uq_tutor_group_assignment"),
        )
        op.create_index(
            "ix_tutor_group_assignment_tutor_active",
            "tutor_group_assignments",
            ["tutor_user_id", "is_active"],
            unique=False,
        )

    if _table_exists(inspector, "qr_sessions") is False:
        op.create_table(
            "qr_sessions",
            sa.Column("lesson_id", sa.Uuid(), nullable=False),
            sa.Column("teacher_id", sa.Uuid(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_slot_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_qr_sessions_lesson_active", "qr_sessions", ["lesson_id", "is_active"], unique=False)
        op.create_index("ix_qr_sessions_teacher_active", "qr_sessions", ["teacher_id", "is_active"], unique=False)

    if _table_exists(inspector, "risk_forecasts") is False:
        op.create_table(
            "risk_forecasts",
            sa.Column("student_id", sa.Uuid(), nullable=False),
            sa.Column("horizon_days", sa.Integer(), nullable=False),
            sa.Column("period_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
            sa.Column("predicted_score", sa.Numeric(5, 2), nullable=False),
            sa.Column("predicted_late_count", sa.Integer(), nullable=False),
            sa.Column("predicted_unexcused_absence_count", sa.Integer(), nullable=False),
            sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default=sa.text("70")),
            sa.Column("explain", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("calculated_for_date", sa.Date(), nullable=False),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_risk_forecasts_student_date",
            "risk_forecasts",
            ["student_id", "calculated_for_date"],
            unique=False,
        )
        op.create_index(
            "ix_risk_forecasts_horizon",
            "risk_forecasts",
            ["horizon_days", "calculated_for_date"],
            unique=False,
        )

    if _table_exists(inspector, "biometric_devices") is False:
        op.create_table(
            "biometric_devices",
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("secret_hash", sa.String(length=128), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allowed_ips", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("device_id"),
        )
        op.create_index("ix_biometric_devices_device_id", "biometric_devices", ["device_id"], unique=False)

    if _table_exists(inspector, "student_biometrics") is False:
        op.create_table(
            "student_biometrics",
            sa.Column("student_id", sa.Uuid(), nullable=False),
            sa.Column("fingerprint_hash", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("fingerprint_hash"),
        )
        op.create_index(
            "ix_student_biometrics_fingerprint_hash",
            "student_biometrics",
            ["fingerprint_hash"],
            unique=False,
        )
        op.create_index(
            "ix_student_biometrics_student_active",
            "student_biometrics",
            ["student_id", "is_active"],
            unique=False,
        )

    if _table_exists(inspector, "biometric_events") is False:
        op.create_table(
            "biometric_events",
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("scanner_event_id", sa.String(length=128), nullable=False),
            sa.Column("lesson_id", sa.Uuid(), nullable=True),
            sa.Column("student_id", sa.Uuid(), nullable=True),
            sa.Column("fingerprint_hash", sa.String(length=255), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("device_id", "scanner_event_id", name="uq_biometric_device_scanner_event"),
        )
        op.create_index("ix_biometric_events_created_at", "biometric_events", ["created_at"], unique=False)
        op.create_index(
            "ix_biometric_events_student_created",
            "biometric_events",
            ["student_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "biometric_events"):
        op.drop_table("biometric_events")
    if _table_exists(inspector, "student_biometrics"):
        op.drop_table("student_biometrics")
    if _table_exists(inspector, "biometric_devices"):
        op.drop_table("biometric_devices")
    if _table_exists(inspector, "risk_forecasts"):
        op.drop_table("risk_forecasts")
    if _table_exists(inspector, "qr_sessions"):
        op.drop_table("qr_sessions")
    if _table_exists(inspector, "tutor_group_assignments"):
        op.drop_table("tutor_group_assignments")
    if _column_exists(inspector, "streams", "is_archived"):
        op.drop_column("streams", "is_archived")
    if _column_exists(inspector, "faculties", "is_archived"):
        op.drop_column("faculties", "is_archived")
