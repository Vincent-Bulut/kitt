"""Baseline: schema as created by Base.metadata.create_all() before Alembic.

Existing databases already have this schema and are stamped at this revision
(see backend/migrate.py); new databases get it created here.

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("isin", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("fees", sa.Float(), nullable=True),
        sa.Column("asset_class", sa.String(), nullable=True),
        sa.Column("geo_focus", sa.String(), nullable=True),
        sa.Column("asset_category_lv1", sa.String(), nullable=True),
        sa.Column("asset_category_lv2", sa.String(), nullable=True),
        sa.Column("asset_category_lv3", sa.String(), nullable=True),
        sa.Column("asset_category_lv4", sa.String(), nullable=True),
    )

    op.create_table(
        "portfolio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("manager_name", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_portfolio_id", "portfolio", ["id"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolio.id"), nullable=False),
        sa.Column("symbol", sa.String(length=50), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("qte", sa.Integer(), nullable=False),
    )
    op.create_index("ix_positions_id", "positions", ["id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id", sa.Integer(), sa.ForeignKey("portfolio.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("symbol", sa.String(length=50), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("side", postgresql.ENUM("BUY", "SELL", name="transaction_side"), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("transaction_fee", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
    )
    op.create_index("ix_transactions_id", "transactions", ["id"])
    op.create_index("ix_transactions_portfolio_id", "transactions", ["portfolio_id"])
    op.create_index("ix_transactions_symbol", "transactions", ["symbol"])
    op.create_index("ix_transactions_portfolio_symbol_date", "transactions", ["portfolio_id", "symbol", "date"])


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("positions")
    op.drop_table("portfolio")
    op.drop_table("assets")
    postgresql.ENUM(name="transaction_side").drop(op.get_bind(), checkfirst=True)
