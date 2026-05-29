from pydantic import BaseModel, Field, model_validator
from enum import Enum, IntEnum
from datetime import date
from typing import List, Optional

class PriorityEnum(IntEnum):
    LOW = 3
    MEDIUM = 2
    HIGH = 1


class TransactionSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Portfolio(BaseModel):
    name: str
    start_date: date
    end_date: date | None = None
    description: str | None = None
    manager_name: str | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date doit être postérieure à start_date")
        return self


class PortfolioRead(Portfolio):
    id: int

    model_config = {
        "from_attributes": True
    }


class TransactionCreate(BaseModel):
    symbol: str
    date: date
    side: TransactionSide
    quantity: float = Field(gt=0, description="Positive quantity; direction is given by `side`")
    price: float = Field(ge=0)
    transaction_fee: float | None = 0.0
    amount: float | None = None
    currency: str | None = None


class TransactionRead(BaseModel):
    id: int
    portfolio_id: int
    symbol: str
    date: date
    side: TransactionSide
    quantity: float
    price: float
    transaction_fee: float | None
    amount: float | None
    currency: str | None

    model_config = {"from_attributes": True}


class PositionViewRow(BaseModel):
    symbol: str
    name: str | None
    currency: str | None
    current_qty: float
    avg_cost: float | None
    cost_basis: float
    market_price: float | None
    market_value: float | None
    weight: float | None
    realized_pnl: float
    unrealized_pnl: float | None
    total_pnl: float | None
    total_fees: float
    estimated_ter_cost_annual: float | None
    contribution_to_portfolio_pnl: float | None
    num_transactions: int
    price_error: str | None = None


class PositionViewResponse(BaseModel):
    portfolio_id: int
    portfolio_name: str
    asof_used: date | None
    total_market_value: float
    total_cost_basis: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl: float
    total_fees: float
    estimated_ter_cost_annual: float
    rows: List[PositionViewRow]
