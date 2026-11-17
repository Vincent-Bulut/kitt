"""Price lookups, cumulative returns and volatility (pure functions)."""

from typing import Any

import numpy as np
import pandas as pd

from backend.api.analytics.schemas import ReturnMode, VolFrequency

_ANNUALIZATION = {
    "daily": 252.0,
    "weekly": 52.0,
    "monthly": 12.0,
}


def nearest_prev_price(series: pd.Series, target: pd.Timestamp) -> tuple[float | None, pd.Timestamp | None]:
    """
    Returns (price, date) for the last available price <= target.
    """
    s = series.loc[:target].dropna()
    if s.empty:
        return None, None
    v = s.iloc[-1]
    price = float(v.item()) if hasattr(v, "item") else float(v)
    return price, s.index[-1]


def cumulative_returns_series_from_prices(
    prices: pd.Series,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp
) -> tuple[pd.Timestamp, float, pd.Series]:
    """
    Return (start_used_date, base_price, cum_return_series_decimal).
    cum_return_series is indexed by date, values in decimal (0.10 = +10%).
    """
    s = prices.dropna().copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s = s.loc[:end_ts]

    base_price, start_used = nearest_prev_price(s, start_ts)
    if base_price is None:
        raise ValueError(f"No price data on or before {start_ts.date()}")

    # Keep data from start_used onwards
    s2 = s.loc[start_used:]
    if s2.empty:
        raise ValueError("No prices after start_date_used")

    cum = (s2 / base_price) - 1.0
    return start_used, float(base_price), cum


def compute_vols(
    prices: pd.Series,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    frequency: VolFrequency,
    return_mode: ReturnMode,
) -> dict[str, Any]:
    """
    - Find start_used/end_used using nearest previous available price (<= requested dates)
    - Compute returns inside [start_used, end_used]
    - Compute BOTH:
        * volatility_period (std of returns)
        * annualized_volatility
    """
    s = prices.dropna().copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)

    # anchor dates (nearest <= requested)
    _, start_used = nearest_prev_price(s, start_ts)
    if start_used is None:
        raise ValueError(f"No price data on or before {start_ts.date()}")

    _, end_used = nearest_prev_price(s, end_ts)
    if end_used is None:
        raise ValueError(f"No price data on or before {end_ts.date()}")

    window = s.loc[start_used:end_used].dropna()
    if len(window) < 3:
        raise ValueError("Not enough price points in window")

    if return_mode == "log":
        rets = np.log(window).diff().dropna()
    else:
        rets = window.pct_change().dropna()

    n = int(rets.shape[0])
    if n < 2:
        raise ValueError("Not enough returns to compute volatility")

    vol_period = float(rets.std(ddof=1))
    ann_factor = float(_ANNUALIZATION[frequency])
    vol_ann = float(vol_period * np.sqrt(ann_factor))

    return {
        "start_used": start_used,
        "end_used": end_used,
        "observations": n,
        "volatility_period": vol_period,
        "annualized_volatility": vol_ann,
    }
