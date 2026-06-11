"""add schedule export type

Revision ID: 0008_schedule_export_type
Revises: 0007_user_phone_number
Create Date: 2026-06-05 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_schedule_export_type"
down_revision: str | None = "0007_user_phone_number"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE export_job_type ADD VALUE IF NOT EXISTS 'schedule'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values without recreating the enum and dependent columns.
    pass
