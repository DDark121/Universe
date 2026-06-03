"""student tg bootstrap and binding request details

Revision ID: 0003_student_tg_bootstrap
Revises: 0002_tutor_qr_biometric_forecast
Create Date: 2026-03-16 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_student_tg_bootstrap"
down_revision: str | None = "0002_tutor_qr_biometric_forecast"
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

    if _column_exists(inspector, "telegram_binding_requests", "group_code") is False:
        op.add_column("telegram_binding_requests", sa.Column("group_code", sa.String(length=64), nullable=True))

    if _column_exists(inspector, "telegram_binding_requests", "note") is False:
        op.add_column("telegram_binding_requests", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _column_exists(inspector, "telegram_binding_requests", "note"):
        op.drop_column("telegram_binding_requests", "note")

    if _column_exists(inspector, "telegram_binding_requests", "group_code"):
        op.drop_column("telegram_binding_requests", "group_code")
