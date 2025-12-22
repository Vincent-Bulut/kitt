import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Date
from sqlalchemy.orm import Mapped, relationship, DeclarativeBase
from sqlalchemy.testing.schema import mapped_column

from backend.api.database import engine

class Base(DeclarativeBase):
    pass

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


class Referential(Base):
    __tablename__ = "referential"

    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Positions(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolio.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), ForeignKey("referential.symbol"), nullable=False)
    qte: Mapped[int] = mapped_column(Integer, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="positions",
    )

    product: Mapped["Referential"] = relationship(
        "Referential",
        lazy="joined",
    )

if __name__ == '__main__':
    Base.metadata.create_all(engine)