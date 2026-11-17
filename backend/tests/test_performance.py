"""Drawdowns, cumulative returns and volatility computed from price series."""

import numpy as np
import pandas as pd
import pytest

from backend.api.analytics import (
    _compute_vols,
    _drawdown_metrics_and_episodes,
    _max_drawdown_path,
    _nearest_prev_price,
    cumulative_returns_series_from_prices,
)


def prices(values, start="2024-01-01") -> pd.Series:
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


# --- nearest previous price ---------------------------------------------------

def test_nearest_prev_price_falls_back_to_last_available_date():
    s = prices([100, 101, 102])  # Mon 1, Tue 2, Wed 3 January 2024
    price, used = _nearest_prev_price(s, pd.Timestamp("2024-01-10"))
    assert price == 102
    assert used == pd.Timestamp("2024-01-03")


def test_nearest_prev_price_before_first_date_returns_none():
    s = prices([100, 101])
    assert _nearest_prev_price(s, pd.Timestamp("2023-12-31")) == (None, None)


# --- drawdowns ----------------------------------------------------------------

def test_max_drawdown_path_finds_peak_trough_and_recovery():
    s = prices([100, 120, 90, 60, 100, 130, 125])
    path = _max_drawdown_path(s)
    assert path["max_drawdown"] == pytest.approx(-0.5)
    assert path["peak_date"] == s.index[1].date().isoformat()
    assert path["trough_date"] == s.index[3].date().isoformat()
    assert path["recovery_date"] == s.index[5].date().isoformat()


def test_max_drawdown_path_without_recovery():
    path = _max_drawdown_path(prices([100, 80, 90]))
    assert path["recovery_date"] is None
    assert path["max_drawdown"] == pytest.approx(-0.2)


def test_drawdown_episodes_and_metrics():
    # Two episodes: 100 -> 90 (recovered at 110), then 110 -> 99 (still open)
    s = prices([100, 90, 95, 110, 99])
    metrics, episodes = _drawdown_metrics_and_episodes(s)

    assert metrics["num_drawdown_episodes"] == 2
    assert metrics["max_drawdown"] == pytest.approx(-0.10)
    assert metrics["current_drawdown"] == pytest.approx(-0.10)
    assert metrics["max_drawdown_length_trading_days"] == 2

    first, second = episodes
    assert first["duration_days"] == 2
    assert first["end_date"] is not None
    assert second["end_date"] is None


def test_monotonic_prices_have_no_drawdown():
    metrics, episodes = _drawdown_metrics_and_episodes(prices([1, 2, 3, 4]))
    assert episodes == []
    assert metrics["max_drawdown"] == 0.0
    assert metrics["num_drawdown_episodes"] == 0


# --- cumulative returns -------------------------------------------------------

def test_cumulative_returns_are_relative_to_base_price():
    s = prices([100, 110, 99, 121])
    start_used, base, cum = cumulative_returns_series_from_prices(s, s.index[0], s.index[-1])
    assert start_used == s.index[0]
    assert base == 100
    np.testing.assert_allclose(cum.to_numpy(), [0.0, 0.10, -0.01, 0.21])


def test_cumulative_returns_respect_end_date():
    s = prices([100, 110, 120, 130])
    _, _, cum = cumulative_returns_series_from_prices(s, s.index[0], s.index[1])
    assert len(cum) == 2


def test_cumulative_returns_raise_without_data_before_start():
    s = prices([100, 110])
    with pytest.raises(ValueError):
        cumulative_returns_series_from_prices(s, pd.Timestamp("2020-01-01"), s.index[-1])


# --- volatility ---------------------------------------------------------------

def test_annualized_volatility_uses_sqrt_of_time():
    rng = np.random.default_rng(7)
    daily = rng.normal(0, 0.01, size=1_000)
    s = prices(100 * np.exp(np.cumsum(daily)))

    out = _compute_vols(s, s.index[0], s.index[-1], "daily", "log")

    assert out["observations"] == len(s) - 1
    assert out["annualized_volatility"] == pytest.approx(out["volatility_period"] * np.sqrt(252))
    assert out["volatility_period"] == pytest.approx(0.01, rel=0.1)


def test_volatility_requires_enough_points():
    s = prices([100, 101])
    with pytest.raises(ValueError):
        _compute_vols(s, s.index[0], s.index[-1], "daily", "arith")
