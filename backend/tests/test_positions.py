"""Weighted-average-cost position accounting."""

import datetime as dt
from types import SimpleNamespace

import pytest

from backend.api.model import TransactionSide
from backend.api.transactions import _compute_position

BUY, SELL = TransactionSide.BUY, TransactionSide.SELL


def tx(id_, day, side, qty, price, fee=0.0):
    return SimpleNamespace(
        id=id_, date=dt.date(2024, 1, day), side=side, quantity=qty, price=price, transaction_fee=fee
    )


def test_buys_accumulate_cost_including_fees():
    pos = _compute_position([tx(1, 1, BUY, 10, 100, fee=5), tx(2, 2, BUY, 10, 120, fee=5)])
    assert pos["current_qty"] == 20
    assert pos["cost_basis"] == pytest.approx(2210)
    assert pos["avg_cost"] == pytest.approx(110.5)
    assert pos["total_fees"] == 10
    assert pos["realized_pnl"] == 0


def test_partial_sell_realizes_pnl_at_average_cost():
    pos = _compute_position([tx(1, 1, BUY, 10, 100), tx(2, 2, BUY, 10, 120), tx(3, 3, SELL, 5, 130, fee=2)])
    # avg cost 110 -> realized (130 - 110) * 5 - 2
    assert pos["realized_pnl"] == pytest.approx(98)
    assert pos["current_qty"] == 15
    assert pos["avg_cost"] == pytest.approx(110)


def test_full_exit_clears_cost_basis():
    pos = _compute_position([tx(1, 1, BUY, 10, 100), tx(2, 2, SELL, 10, 90)])
    assert pos["current_qty"] == 0
    assert pos["cost_basis"] == 0
    assert pos["avg_cost"] is None
    assert pos["realized_pnl"] == pytest.approx(-100)


def test_transactions_are_processed_in_date_order():
    shuffled = [tx(2, 5, SELL, 10, 150), tx(1, 1, BUY, 10, 100)]
    pos = _compute_position(shuffled)
    assert pos["realized_pnl"] == pytest.approx(500)
    assert pos["num_transactions"] == 2
