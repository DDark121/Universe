"""add faq assistant support and tg delivery extensions

Revision ID: 0005_ai_faq_tg_extensions
Revises: 0004_telegram_ids_bigint
Create Date: 2026-03-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_ai_faq_tg_extensions"
down_revision: str | None = "0004_telegram_ids_bigint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in ("groups", "disciplines"):
        if not _column_exists(inspector, table_name, "window_start_offset_override_minutes"):
            op.add_column(table_name, sa.Column("window_start_offset_override_minutes", sa.Integer(), nullable=True))
        if not _column_exists(inspector, table_name, "window_duration_override_minutes"):
            op.add_column(table_name, sa.Column("window_duration_override_minutes", sa.Integer(), nullable=True))
        if not _column_exists(inspector, table_name, "late_threshold_override_minutes"):
            op.add_column(table_name, sa.Column("late_threshold_override_minutes", sa.Integer(), nullable=True))

    if not _table_exists(inspector, "group_telegram_chats"):
        op.create_table(
            "group_telegram_chats",
            sa.Column("group_id", sa.Uuid(), nullable=False),
            sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_group_telegram_chats")),
            sa.UniqueConstraint("group_id", name=op.f("uq_group_telegram_chats_group_id")),
            sa.UniqueConstraint("telegram_chat_id", name=op.f("uq_group_telegram_chats_telegram_chat_id")),
        )
    if _table_exists(inspector, "group_telegram_chats") and not _index_exists(
        inspector,
        "group_telegram_chats",
        "ix_group_telegram_chats_telegram_chat_id",
    ):
        op.create_index(
            op.f("ix_group_telegram_chats_telegram_chat_id"),
            "group_telegram_chats",
            ["telegram_chat_id"],
            unique=True,
        )

    if not _table_exists(inspector, "lesson_activity_scores"):
        op.create_table(
            "lesson_activity_scores",
            sa.Column("lesson_id", sa.Uuid(), nullable=False),
            sa.Column("student_id", sa.Uuid(), nullable=False),
            sa.Column("score", sa.Numeric(6, 2), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("recorded_by", sa.Uuid(), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_activity_scores")),
            sa.UniqueConstraint("lesson_id", "student_id", name="uq_activity_score_lesson_student"),
        )
    if _table_exists(inspector, "lesson_activity_scores") and not _index_exists(
        inspector,
        "lesson_activity_scores",
        "ix_activity_score_student",
    ):
        op.create_index("ix_activity_score_student", "lesson_activity_scores", ["student_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "lesson_activity_scores"):
        if _index_exists(inspector, "lesson_activity_scores", "ix_activity_score_student"):
            op.drop_index("ix_activity_score_student", table_name="lesson_activity_scores")
        op.drop_table("lesson_activity_scores")

    if _table_exists(inspector, "group_telegram_chats"):
        if _index_exists(inspector, "group_telegram_chats", op.f("ix_group_telegram_chats_telegram_chat_id")):
            op.drop_index(op.f("ix_group_telegram_chats_telegram_chat_id"), table_name="group_telegram_chats")
        op.drop_table("group_telegram_chats")

    for table_name in ("disciplines", "groups"):
        if _column_exists(inspector, table_name, "late_threshold_override_minutes"):
            op.drop_column(table_name, "late_threshold_override_minutes")
        if _column_exists(inspector, table_name, "window_duration_override_minutes"):
            op.drop_column(table_name, "window_duration_override_minutes")
        if _column_exists(inspector, table_name, "window_start_offset_override_minutes"):
            op.drop_column(table_name, "window_start_offset_override_minutes")
