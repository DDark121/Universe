"""add user phone number

Revision ID: 0007_user_phone_number
Revises: 0006_ai_import_drafts
Create Date: 2026-03-31 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_user_phone_number"
down_revision: str | None = "0006_ai_import_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _unique_constraint_exists(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    return any(constraint["name"] == constraint_name for constraint in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _column_exists(inspector, "users", "phone_number"):
        op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))

    inspector = sa.inspect(bind)
    if not _unique_constraint_exists(inspector, "users", "uq_users_phone_number"):
        op.create_unique_constraint("uq_users_phone_number", "users", ["phone_number"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _unique_constraint_exists(inspector, "users", "uq_users_phone_number"):
        op.drop_constraint("uq_users_phone_number", "users", type_="unique")

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "users", "phone_number"):
        op.drop_column("users", "phone_number")
