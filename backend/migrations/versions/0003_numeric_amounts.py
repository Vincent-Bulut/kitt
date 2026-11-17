"""Store quantities, prices, fees and amounts as exact NUMERIC instead of FLOAT.

Binary floats cannot represent most decimal amounts (e.g. 293 * 102.7 was
stored as 30091.100000000002). Existing values are rounded to the new scale.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, new type)
COLUMNS = [
    ("transactions", "quantity", sa.Numeric(20, 8)),
    ("transactions", "price", sa.Numeric(20, 8)),
    ("transactions", "transaction_fee", sa.Numeric(20, 6)),
    ("transactions", "amount", sa.Numeric(20, 6)),
    ("assets", "fees", sa.Numeric(8, 6)),
]


def upgrade() -> None:
    for table, column, type_ in COLUMNS:
        op.alter_column(
            table,
            column,
            type_=type_,
            existing_type=sa.Float(),
            postgresql_using=f"round({column}::numeric, {type_.scale})",
        )


def downgrade() -> None:
    for table, column, type_ in COLUMNS:
        op.alter_column(table, column, type_=sa.Float(), existing_type=type_)
