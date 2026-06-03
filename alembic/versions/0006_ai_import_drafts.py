"""add ai import drafts

Revision ID: 0006_ai_import_drafts
Revises: 0005_ai_faq_tg_extensions
Create Date: 2026-03-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_ai_import_drafts"
down_revision: str | None = "0005_ai_faq_tg_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "ai_import_drafts"):
        op.create_table(
            "ai_import_drafts",
            sa.Column("created_by", sa.Uuid(), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "queued",
                    "processing",
                    "draft",
                    "applied",
                    "failed",
                    "rejected",
                    name="ai_import_draft_status",
                ),
                nullable=False,
                server_default="queued",
            ),
            sa.Column(
                "mode",
                sa.Enum("mixed", "users", "schedule", name="ai_import_mode"),
                nullable=False,
            ),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_path", sa.String(length=512), nullable=False),
            sa.Column("wizard", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("summary", sa.JSON(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("issues", sa.JSON(), nullable=True),
            sa.Column("apply_result", sa.JSON(), nullable=True),
            sa.Column("error_report", sa.JSON(), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_import_drafts")),
        )
    if _table_exists(inspector, "ai_import_drafts") and not _index_exists(
        inspector,
        "ai_import_drafts",
        "ix_ai_import_drafts_status_created",
    ):
        op.create_index(
            "ix_ai_import_drafts_status_created",
            "ai_import_drafts",
            ["status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "ai_import_drafts"):
        if _index_exists(inspector, "ai_import_drafts", "ix_ai_import_drafts_status_created"):
            op.drop_index("ix_ai_import_drafts_status_created", table_name="ai_import_drafts")
        op.drop_table("ai_import_drafts")

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TYPE IF EXISTS ai_import_mode")
    op.execute("DROP TYPE IF EXISTS ai_import_draft_status")
