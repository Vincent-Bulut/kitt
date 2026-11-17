"""Thread-safe access to yfinance.

FastAPI runs the (synchronous) endpoints in a thread pool, so several requests
can call yfinance at the same time. yfinance is not thread-safe: `yf.download`
collects its results in a module-level dict (`yfinance.shared._DFS`) that every
call resets, and `Ticker.history` writes to the same dict on errors. Concurrent
calls therefore receive each other's tickers or price series, silently.

Every yfinance network call in the application must go through this module,
which serialises them behind a single lock. Results are cached upstream
(10-minute TTL), so the throughput cost is small.
"""

import threading
from typing import Any

import pandas as pd
import yfinance as yf

_YF_LOCK = threading.RLock()


def download(**kwargs: Any) -> pd.DataFrame | None:
    """`yf.download` with the same arguments, safe to call from several threads."""
    with _YF_LOCK:
        df = yf.download(**kwargs)
        # Detach the result from yfinance's shared state before releasing the lock
        return None if df is None else df.copy()


def history(ticker: str, **kwargs: Any) -> pd.DataFrame:
    """`yf.Ticker(ticker).history(...)`, safe to call from several threads."""
    with _YF_LOCK:
        return yf.Ticker(ticker).history(**kwargs).copy()


def quote_currency(ticker: str) -> str | None:
    """Quote currency reported by Yahoo (may be a minor unit such as 'GBp'); None if unavailable."""
    with _YF_LOCK:
        try:
            return yf.Ticker(ticker).fast_info["currency"]
        except Exception:
            return None
