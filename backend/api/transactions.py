from typing import List, Dict, Tuple
from datetime import date as date_type

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.api import model, schema
from backend.api.database import get_db

router = APIRouter(tags=["TRANSACTIONS"])


# =============================================================
# Transaction CRUD
# =============================================================

@router.post(
    "/portfolios/{portfolio_id}/transactions",
    response_model=schema.TransactionRead,
    status_code=201,
)
def create_transaction(
    portfolio_id: int,
    payload: schema.TransactionCreate,
    db: Session = Depends(get_db),
):
    portfolio = db.get(model.Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio introuvable.")

    asset = db.get(model.Assets, payload.symbol)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset '{payload.symbol}' introuvable.")

    amount = payload.amount if payload.amount is not None else payload.quantity * payload.price
    currency = payload.currency or asset.currency

    try:
        tx = model.Transaction(
            portfolio_id=portfolio_id,
            symbol=payload.symbol,
            date=payload.date,
            side=model.TransactionSide(payload.side.value),
            quantity=payload.quantity,
            price=payload.price,
            transaction_fee=payload.transaction_fee or 0.0,
            amount=amount,
            currency=currency,
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/portfolios/{portfolio_id}/transactions",
    response_model=List[schema.TransactionRead],
)
def list_transactions(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = db.get(model.Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio introuvable.")
    return (
        db.query(model.Transaction)
        .filter(model.Transaction.portfolio_id == portfolio_id)
        .order_by(model.Transaction.date.asc(), model.Transaction.id.asc())
        .all()
    )


@router.get("/transactions/{transaction_id}", response_model=schema.TransactionRead)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    tx = db.get(model.Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction introuvable.")
    return tx


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    tx = db.get(model.Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction introuvable.")
    db.delete(tx)
    db.commit()
    return {"message": "Transaction supprimée avec succès"}


# =============================================================
# Position view (computed)
# =============================================================

def _fetch_last_prices(symbols: List[str]) -> Tuple[Dict[str, float], Dict[str, str], date_type | None]:
    """Return (prices, errors, asof_used).

    Uses yfinance.download for a multi-ticker single call. Picks the most
    recent non-NaN close for each symbol.
    """
    prices: Dict[str, float] = {}
    errors: Dict[str, str] = {}
    asof_used: date_type | None = None

    if not symbols:
        return prices, errors, asof_used

    try:
        df = yf.download(
            tickers=symbols,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker" if len(symbols) > 1 else "column",
            threads=True,
        )
    except Exception as e:
        for s in symbols:
            errors[s] = f"yfinance download failed: {e}"
        return prices, errors, asof_used

    if df is None or df.empty:
        for s in symbols:
            errors[s] = "No price data returned by yfinance"
        return prices, errors, asof_used

    def _fetch_last_prices(symbols: List[str]) -> Tuple[Dict[str, float], Dict[str, str], date_type | None]:
        """Return (prices, errors, asof_used).

        Uses yfinance.download for a multi-ticker single call. Picks the most
        recent non-NaN close for each symbol.
        """
    prices: Dict[str, float] = {}
    errors: Dict[str, str] = {}
    asof_used: date_type | None = None

    if not symbols:
        return prices, errors, asof_used

    try:
        df = yf.download(
            tickers=symbols,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker" if len(symbols) > 1 else "column",
            threads=True,
        )
    except Exception as e:
        for s in symbols:
            errors[s] = f"yfinance download failed: {e}"
        return prices, errors, asof_used

    if df is None or df.empty:
        for s in symbols:
            errors[s] = "No price data returned by yfinance"
        return prices, errors, asof_used

    def _pick_close(close_data: pd.Series | pd.DataFrame) -> Tuple[float | None, date_type | None]:
        if isinstance(close_data, pd.DataFrame):
            if close_data.empty:
                return None, None

            # If yfinance returns duplicate or multi-column Close data,
            # take the first column that contains valid numeric close values.
            for column in close_data.columns:
                series = pd.to_numeric(close_data[column], errors="coerce").dropna()
                if not series.empty:
                    last_ts = pd.to_datetime(series.index[-1])
                    return float(series.iloc[-1]), last_ts.date()

            return None, None

        series = pd.to_numeric(close_data, errors="coerce").dropna()
        if series.empty:
            return None, None

        last_ts = pd.to_datetime(series.index[-1])
        return float(series.iloc[-1]), last_ts.date()

    if len(symbols) == 1:
        sym = symbols[0]
        close_col = df["Close"] if "Close" in df.columns else None
        if close_col is None:
            errors[sym] = "Close column missing"
        else:
            last_price, last_date = _pick_close(close_col)
            if last_price is None:
                errors[sym] = "No close data"
            else:
                prices[sym] = last_price
                if asof_used is None or (last_date and last_date > asof_used):
                    asof_used = last_date
    else:
        for sym in symbols:
            try:
                sub = df[sym] if sym in df.columns.get_level_values(0) else None
                if sub is None or "Close" not in sub.columns:
                    errors[sym] = "No close data"
                    continue
                last_price, last_date = _pick_close(sub["Close"])
                if last_price is None:
                    errors[sym] = "No close data"
                    continue
                prices[sym] = last_price
                if asof_used is None or (last_date and last_date > asof_used):
                    asof_used = last_date
            except Exception as e:
                errors[sym] = f"price extraction error: {e}"

    return prices, errors, asof_used


def _compute_position(transactions: List[model.Transaction]) -> dict:
    """Weighted Average Cost (WAC) accumulator for a single (portfolio, symbol).

    Returns: dict with current_qty, cost_basis, avg_cost, realized_pnl, total_fees, num_transactions.

    Convention:
      BUY:  cost_basis += qty * price + fee; qty += qty;          fees += fee
      SELL: realized   += (price - avg_cost) * qty - fee;
            cost_basis -= avg_cost * qty;
            qty        -= qty;
            fees       += fee
    """
    qty = 0.0
    cost_basis = 0.0
    realized = 0.0
    fees_total = 0.0

    txs = sorted(transactions, key=lambda t: (t.date, t.id))
    for tx in txs:
        fee = float(tx.transaction_fee or 0.0)
        fees_total += fee
        if tx.side == model.TransactionSide.BUY:
            cost_basis += tx.quantity * tx.price + fee
            qty += tx.quantity
        else:  # SELL
            if qty <= 0:
                # Selling without an existing long position — treat as realized P&L with no cost basis.
                realized += tx.quantity * tx.price - fee
                # qty would go negative (short); we still track it.
                qty -= tx.quantity
                continue
            sell_qty = min(tx.quantity, qty)
            avg_cost = cost_basis / qty if qty > 0 else 0.0
            realized += (tx.price - avg_cost) * sell_qty - fee
            cost_basis -= avg_cost * sell_qty
            qty -= sell_qty
            # If we sold more than we held (short), record the excess at zero cost basis.
            excess = tx.quantity - sell_qty
            if excess > 0:
                realized += excess * tx.price
                qty -= excess

    avg_cost = (cost_basis / qty) if qty > 0 else None
    return {
        "current_qty": qty,
        "cost_basis": cost_basis if qty > 0 else 0.0,
        "avg_cost": avg_cost,
        "realized_pnl": realized,
        "total_fees": fees_total,
        "num_transactions": len(txs),
    }


@router.get(
    "/portfolios/{portfolio_id}/positions-view",
    response_model=schema.PositionViewResponse,
)
def get_positions_view(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = db.get(model.Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio introuvable.")

    txs = (
        db.query(model.Transaction)
        .filter(model.Transaction.portfolio_id == portfolio_id)
        .all()
    )

    if not txs:
        return schema.PositionViewResponse(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            asof_used=None,
            total_market_value=0.0,
            total_cost_basis=0.0,
            total_realized_pnl=0.0,
            total_unrealized_pnl=0.0,
            total_pnl=0.0,
            total_fees=0.0,
            estimated_ter_cost_annual=0.0,
            rows=[],
        )

    by_symbol: Dict[str, List[model.Transaction]] = {}
    for tx in txs:
        by_symbol.setdefault(tx.symbol, []).append(tx)

    symbols = list(by_symbol.keys())
    prices, price_errors, asof_used = _fetch_last_prices(symbols)

    raw_rows: List[dict] = []
    for sym, sym_txs in by_symbol.items():
        agg = _compute_position(sym_txs)
        asset = sym_txs[0].asset
        market_price = prices.get(sym)
        market_value = (
            agg["current_qty"] * market_price if (market_price is not None and agg["current_qty"] > 0) else None
        )
        unrealized = (
            (market_value - agg["cost_basis"]) if market_value is not None else None
        )
        total_pnl = (
            agg["realized_pnl"] + (unrealized if unrealized is not None else 0.0)
            if unrealized is not None
            else None
        )
        # estimated TER cost (annual): market_value * asset.fees
        # assumption: asset.fees is in DECIMAL form (e.g. 0.0007 for 7bps)
        ter_cost = None
        if market_value is not None and asset.fees is not None:
            ter_cost = market_value * float(asset.fees)

        raw_rows.append({
            "symbol": sym,
            "name": asset.name if asset else None,
            "currency": asset.currency if asset else None,
            "current_qty": agg["current_qty"],
            "avg_cost": agg["avg_cost"],
            "cost_basis": agg["cost_basis"],
            "market_price": market_price,
            "market_value": market_value,
            "realized_pnl": agg["realized_pnl"],
            "unrealized_pnl": unrealized,
            "total_pnl": total_pnl,
            "total_fees": agg["total_fees"],
            "estimated_ter_cost_annual": ter_cost,
            "num_transactions": agg["num_transactions"],
            "price_error": price_errors.get(sym),
        })

    # Portfolio-level aggregates
    total_market_value = sum((r["market_value"] or 0.0) for r in raw_rows)
    total_cost_basis = sum(r["cost_basis"] for r in raw_rows)
    total_realized = sum(r["realized_pnl"] for r in raw_rows)
    total_unrealized = sum((r["unrealized_pnl"] or 0.0) for r in raw_rows)
    total_pnl = total_realized + total_unrealized
    total_fees = sum(r["total_fees"] for r in raw_rows)
    total_ter = sum((r["estimated_ter_cost_annual"] or 0.0) for r in raw_rows)

    rows: List[schema.PositionViewRow] = []
    for r in raw_rows:
        weight = (
            (r["market_value"] / total_market_value)
            if (r["market_value"] is not None and total_market_value > 0)
            else None
        )
        contribution = (
            ((r["total_pnl"] or 0.0) / total_pnl)
            if (r["total_pnl"] is not None and total_pnl != 0)
            else None
        )
        rows.append(schema.PositionViewRow(
            symbol=r["symbol"],
            name=r["name"],
            currency=r["currency"],
            current_qty=r["current_qty"],
            avg_cost=r["avg_cost"],
            cost_basis=r["cost_basis"],
            market_price=r["market_price"],
            market_value=r["market_value"],
            weight=weight,
            realized_pnl=r["realized_pnl"],
            unrealized_pnl=r["unrealized_pnl"],
            total_pnl=r["total_pnl"],
            total_fees=r["total_fees"],
            estimated_ter_cost_annual=r["estimated_ter_cost_annual"],
            contribution_to_portfolio_pnl=contribution,
            num_transactions=r["num_transactions"],
            price_error=r["price_error"],
        ))

    # Sort by descending market value for the response
    rows.sort(key=lambda r: (r.market_value or 0.0), reverse=True)

    return schema.PositionViewResponse(
        portfolio_id=portfolio.id,
        portfolio_name=portfolio.name,
        asof_used=asof_used,
        total_market_value=total_market_value,
        total_cost_basis=total_cost_basis,
        total_realized_pnl=total_realized,
        total_unrealized_pnl=total_unrealized,
        total_pnl=total_pnl,
        total_fees=total_fees,
        estimated_ter_cost_annual=total_ter,
        rows=rows,
    )
