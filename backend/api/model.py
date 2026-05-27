import datetime
import enum
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Date, Float, Enum, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, relationship, DeclarativeBase
from sqlalchemy.testing.schema import mapped_column

from backend.api.database import engine

class Base(DeclarativeBase):
    pass


class TransactionSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class Portfolio(Base):
    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    positions: Mapped[list["Positions"]] = relationship(
        "Positions",
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="Transaction.date",
    )


class Assets(Base):
    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    fees: Mapped[float] = mapped_column(Float, nullable=True)
    asset_class: Mapped[str] = mapped_column(String, nullable=True)
    geo_focus: Mapped[str] = mapped_column(String, nullable=True)
    asset_category_lv1: Mapped[str] = mapped_column(String, nullable=True)
    asset_category_lv2: Mapped[str] = mapped_column(String, nullable=True)
    asset_category_lv3: Mapped[str] = mapped_column(String, nullable=True)
    asset_category_lv4: Mapped[str] = mapped_column(String, nullable=True)


class Positions(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", name="uq_positions_portfolio_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(
        String(50), ForeignKey("assets.symbol"), nullable=False, index=True
    )

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="positions",
    )

    product: Mapped["Assets"] = relationship(
        "Assets",
        lazy="joined",
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_portfolio_symbol_date", "portfolio_id", "symbol", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(
        String(50), ForeignKey("assets.symbol"), nullable=False, index=True
    )

    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    side: Mapped[TransactionSide] = mapped_column(
        Enum(TransactionSide, name="transaction_side"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_fee: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="transactions",
    )

    asset: Mapped["Assets"] = relationship(
        "Assets",
        lazy="joined",
    )


if __name__ == '__main__':
    Base.metadata.create_all(engine)
