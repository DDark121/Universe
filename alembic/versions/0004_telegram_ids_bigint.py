"""store telegram identifiers as bigint

Revision ID: 0004_telegram_ids_bigint
Revises: 0003_student_tg_bootstrap
Create Date: 2026-03-17 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_telegram_ids_bigint"
down_revision: str | None = "0003_student_tg_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TELEGRAM_ID_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("telegram_accounts", "telegram_id", False),
    ("invite_activations", "telegram_id", True),
    ("telegram_binding_requests", "telegram_id", False),
    ("notification_outbox", "recipient_telegram_id", True),
    ("broadcast_recipients", "telegram_id", True),
)

_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _assert_int32_safe(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            f"""
            SELECT EXISTS (
                SELECT 1
                FROM {table_name}
                WHERE {column_name} IS NOT NULL
                  AND ({column_name} < :min_value OR {column_name} > :max_value)
            )
            """
        ),
        {"min_value": _INT32_MIN, "max_value": _INT32_MAX},
    ).scalar_one()
    if result:
        raise RuntimeError(f"Cannot downgrade {table_name}.{column_name} to INTEGER: values exceed int32 range")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, column_name, nullable in _TELEGRAM_ID_COLUMNS:
        if _column_exists(inspector, table_name, column_name):
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=nullable,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, column_name, nullable in _TELEGRAM_ID_COLUMNS:
        if _column_exists(inspector, table_name, column_name):
            _assert_int32_safe(table_name, column_name)
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=nullable,
            )
