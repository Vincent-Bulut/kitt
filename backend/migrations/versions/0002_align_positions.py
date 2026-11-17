"""Align the positions table with the model.

create_all() never alters existing tables, so the database kept the legacy
`qte` column (NOT NULL, absent from the model: any ORM insert would fail) and
missed the unique constraint, indexes and cascade declared on Positions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("positions", "qte")
    op.create_unique_constraint("uq_positions_portfolio_symbol", "positions", ["portfolio_id", "symbol"])
    op.create_index("ix_positions_portfolio_id", "positions", ["portfolio_id"])
    op.create_index("ix_positions_symbol", "positions", ["symbol"])
    op.drop_constraint("positions_portfolio_id_fkey", "positions", type_="foreignkey")
    op.create_foreign_key(
        "positions_portfolio_id_fkey", "positions", "portfolio", ["portfolio_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("positions_portfolio_id_fkey", "positions", type_="foreignkey")
    op.create_foreign_key("positions_portfolio_id_fkey", "positions", "portfolio", ["portfolio_id"], ["id"])
    op.drop_index("ix_positions_symbol", table_name="positions")
    op.drop_index("ix_positions_portfolio_id", table_name="positions")
    op.drop_constraint("uq_positions_portfolio_symbol", "positions", type_="unique")
    op.add_column("positions", sa.Column("qte", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("positions", "qte", server_default=None)
