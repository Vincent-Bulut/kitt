"""Market data access: Yahoo Finance prices, quote currencies and FX conversion.

This is the only module of the analytics package doing network I/O."""

import pandas as pd

from backend.api import yahoo_client
from backend.api.analytics.schemas import VolFrequency
from backend.api.cache import TTLStore

_INTERVAL_MAP = {
    "daily": "1d",
    "weekly": "1wk",
    "monthly": "1mo",
}

# Quote currency per ticker barely ever changes: keep it for a day
CURRENCY_CACHE = TTLStore(maxsize=5000, ttl=86400)

PERIOD_DAYS = {
    "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "2Y": 730, "3Y": 1095,
    "5Y": 1825, "10Y": 3650,
}

def download_prices_close(
    tickers: list[str],
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    auto_adjust: bool,
) -> pd.DataFrame:
    """
    Download Close prices (auto_adjust => economically adjusted close) for several tickers.
    Retourne DataFrame index date, colonnes tickers.
    """
    fetch_start = (start_ts - pd.Timedelta(days=10)).date().isoformat()
    fetch_end = (end_ts + pd.Timedelta(days=1)).date().isoformat()

    df = yahoo_client.download(
        tickers=tickers,
        start=fetch_start,
        end=fetch_end,
        interval="1d",
        auto_adjust=auto_adjust,
        progress=False,
        group_by="column",
        threads=True,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance multi-tickers: colonnes MultiIndex (Field, Ticker) ou (Ticker, Field) selon versions
    # Extract "Close" robustly whatever the column layout.
    if isinstance(df.columns, pd.MultiIndex):
        # Most common case: level 0 = price field ("Close", "Open"...), level 1 = ticker
        if "Close" in df.columns.get_level_values(0):
            close = df["Close"]
        # Autre cas: niveau 1 = field
        elif "Close" in df.columns.get_level_values(1):
            close = df.xs("Close", axis=1, level=1)
        else:
            raise ValueError("Could not find 'Close' in downloaded data")
    else:
        # Un seul ticker -> colonnes simples
        if "Close" not in df.columns:
            raise ValueError("Could not find 'Close' in downloaded data")
        close = df[["Close"]]
        close.columns = [tickers[0]]

    close = close.dropna(how="all").copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)

    # Trim to the requested window (keep dates <= end_ts)
    close = close.loc[:end_ts]
    return close


def download_close_multi(
    tickers: list[str],
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    auto_adjust: bool,
) -> pd.DataFrame:
    df = yahoo_client.download(
        tickers=tickers,
        start=(start_ts - pd.Timedelta(days=5)).date().isoformat(),
        end=(end_ts + pd.Timedelta(days=1)).date().isoformat(),
        interval="1d",
        auto_adjust=auto_adjust,
        progress=False,
        threads=True,
        group_by="column",
    )
    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            close = df["Close"]
        elif "Close" in df.columns.get_level_values(1):
            close = df.xs("Close", axis=1, level=1)
        else:
            raise ValueError("Could not find 'Close' in yfinance download")
    else:
        if "Close" not in df.columns:
            raise ValueError("Could not find 'Close' in yfinance download")
        close = df[["Close"]]
        close.columns = [tickers[0]]

    close = close.dropna(how="all").copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.loc[start_ts:end_ts]


def download_close_multi_interval(
    tickers: list[str],
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    auto_adjust: bool,
    frequency: VolFrequency,
) -> pd.DataFrame:
    """
    Download Close series with BUFFER BEFORE start_ts.
    IMPORTANT: Do NOT slice to start_ts, only to end_ts, otherwise nearest-prev-start fails
    for non-trading start dates (weekends/holidays).
    """
    interval = _INTERVAL_MAP[frequency]

    # buffer before start is key (weekly/monthly anchors + non-trading days)
    fetch_start = (start_ts - pd.Timedelta(days=60)).date().isoformat()
    fetch_end = (end_ts + pd.Timedelta(days=5)).date().isoformat()

    df = yahoo_client.download(
        tickers=tickers,
        start=fetch_start,
        end=fetch_end,
        interval=interval,
        auto_adjust=auto_adjust,
        progress=False,
        threads=True,
        group_by="column",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # Extract Close robustly (MultiIndex or single)
    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            close = df["Close"]
        elif "Close" in df.columns.get_level_values(1):
            close = df.xs("Close", axis=1, level=1)
        else:
            raise ValueError("Could not find 'Close' in yfinance download")
    else:
        if "Close" not in df.columns:
            raise ValueError("Could not find 'Close' in yfinance download")
        close = df[["Close"]]
        close.columns = [tickers[0]]

    close = close.dropna(how="all").copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)

    close = close.loc[:end_ts]
    return close


def download_close_daily_multi(
    tickers: list[str],
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    auto_adjust: bool,
) -> pd.DataFrame:
    """
    Daily close multi-tickers with BUFFER BEFORE start_ts.
    IMPORTANT: slice only to end_ts, not start_ts.
    """
    fetch_start = (start_ts - pd.Timedelta(days=60)).date().isoformat()
    fetch_end = (end_ts + pd.Timedelta(days=5)).date().isoformat()

    df = yahoo_client.download(
        tickers=tickers,
        start=fetch_start,
        end=fetch_end,
        interval="1d",
        auto_adjust=auto_adjust,
        progress=False,
        threads=True,
        group_by="column",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            close = df["Close"]
        elif "Close" in df.columns.get_level_values(1):
            close = df.xs("Close", axis=1, level=1)
        else:
            raise ValueError("Could not find 'Close' in yfinance download")
    else:
        if "Close" not in df.columns:
            raise ValueError("Could not find 'Close' in yfinance download")
        close = df[["Close"]]
        close.columns = [tickers[0]]

    close = close.dropna(how="all").copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)

    return close.loc[:end_ts]


# Yahoo quotes some listings in minor units (LSE in pence, JSE in cents...)
_MINOR_CURRENCY_UNITS = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}


def _ticker_currency(ticker: str) -> str | None:
    """Quote currency reported by Yahoo (may be a minor unit such as 'GBp')."""
    cached = CURRENCY_CACHE.get(ticker)
    if cached is not None:
        return cached
    currency = yahoo_client.quote_currency(ticker)
    if currency:
        CURRENCY_CACHE.set(ticker, currency)
    return currency


def convert_close_to_base(
    close: pd.DataFrame,
    base_currency: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """
    Express every price series of `close` in `base_currency`, using Yahoo FX
    closes ('USDEUR=X' = EUR per 1 USD), forward-filled onto the price dates.
    Returns the converted prices, the quote currency of each ticker and warnings.
    """
    currencies: dict[str, str] = {}
    warnings: list[str] = []
    factors: dict[str, tuple[str, float]] = {}

    for ticker in close.columns:
        quote = _ticker_currency(ticker)
        if not quote:
            warnings.append(f"Currency of {ticker} unknown on Yahoo — assumed {base_currency}")
            quote = base_currency
        currencies[ticker] = quote
        factors[ticker] = _MINOR_CURRENCY_UNITS.get(quote, (quote.upper(), 1.0))

    foreign = sorted({ccy for ccy, _ in factors.values() if ccy != base_currency})
    fx = pd.DataFrame()
    if foreign:
        fx_tickers = [f"{ccy}{base_currency}=X" for ccy in foreign]
        fx = download_close_daily_multi(fx_tickers, start_ts, end_ts, auto_adjust=False)
        fx = fx.reindex(close.index.union(fx.index)).sort_index().ffill().reindex(close.index)

    converted = close.copy()
    for ticker, (ccy, scale) in factors.items():
        series = close[ticker] * scale
        if ccy != base_currency:
            pair = f"{ccy}{base_currency}=X"
            if pair not in fx.columns or fx[pair].dropna().empty:
                warnings.append(f"No {pair} rate on Yahoo — {ticker} left in {ccy}")
            else:
                series = series * fx[pair]
        converted[ticker] = series

    return converted, currencies, warnings
