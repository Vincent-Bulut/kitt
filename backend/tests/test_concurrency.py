"""Concurrency: yfinance calls and in-memory caches under parallel requests.

FastAPI runs synchronous endpoints in a thread pool. These tests reproduce the
yfinance shared-state race with a fake `yf.download` that behaves like the real
one (module-level result dict reset by every call) and check that the
application's yahoo_client serialises calls correctly.
"""

import contextlib
import threading
import time

import numpy as np
import pandas as pd
import pytest

from backend.api import yahoo_client
from backend.api.analytics import market_data
from backend.api.cache import TTLStore

N_THREADS = 8


class FakeYahoo:
    """Mimics yfinance.download: results go through a module-level dict that each call resets."""

    def __init__(self):
        self.shared: dict[str, pd.Series] = {}

    def download(self, tickers, start, end, **_):
        self.shared = {}  # yfinance does `shared._DFS = {}` at the start of every download
        dates = pd.bdate_range(start, end)
        for t in tickers:
            time.sleep(0.002)  # network latency: lets other threads interleave
            # Price encodes the ticker and the requested start date, so any mix-up is detectable
            self.shared[t] = pd.Series(float(sum(map(ord, t))) + pd.Timestamp(start).dayofyear, index=dates)
        time.sleep(0.002)
        close = pd.DataFrame(self.shared)
        close.columns = pd.MultiIndex.from_product([["Close"], close.columns])
        return close


def _expected_price(ticker: str, start_ts: pd.Timestamp) -> float:
    fetch_start = (start_ts - pd.Timedelta(days=60)).normalize()
    return float(sum(map(ord, ticker))) + fetch_start.dayofyear


def _run_concurrent_downloads():
    """Each thread asks for its own tickers and window; returns the list of mismatches."""
    requests = [
        ([f"T{i}A", f"T{i}B"], pd.Timestamp("2024-03-01") + pd.Timedelta(days=7 * i)) for i in range(N_THREADS)
    ]
    barrier = threading.Barrier(N_THREADS)
    mismatches = []

    def worker(tickers, start_ts):
        barrier.wait()
        close = market_data.download_close_daily_multi(tickers, start_ts, start_ts + pd.Timedelta(days=30), True)
        if sorted(close.columns) != sorted(tickers):
            mismatches.append((tickers, list(close.columns)))
            return
        for t in tickers:
            if not np.allclose(close[t].dropna(), _expected_price(t, start_ts)):
                mismatches.append((tickers, f"wrong prices for {t}"))

    threads = [threading.Thread(target=worker, args=r) for r in requests]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return mismatches


@pytest.fixture
def fake_yahoo(monkeypatch):
    fake = FakeYahoo()
    monkeypatch.setattr(yahoo_client.yf, "download", fake.download)
    return fake


def test_race_is_reproduced_without_the_lock(fake_yahoo, monkeypatch):
    # Sanity check of the test itself: with the lock disabled, results get mixed up
    monkeypatch.setattr(yahoo_client, "_YF_LOCK", contextlib.nullcontext())
    assert _run_concurrent_downloads(), "the fake should exhibit the yfinance race without a lock"


def test_concurrent_downloads_get_their_own_data(fake_yahoo):
    assert _run_concurrent_downloads() == []


def test_downloaded_frame_is_detached_from_shared_state(fake_yahoo):
    close = yahoo_client.download(tickers=["AAA"], start="2024-01-01", end="2024-01-10")
    fake_yahoo.shared["AAA"].iloc[:] = -1.0
    assert (close[("Close", "AAA")] > 0).all()


# --- TTLStore -----------------------------------------------------------------

def test_ttl_store_get_set_and_default():
    store = TTLStore(maxsize=10, ttl=60)
    assert store.get("k") is None
    assert store.get("k", "default") == "default"
    store.set("k", 42)
    assert store.get("k") == 42


def test_ttl_store_expired_entry_returns_default_instead_of_raising():
    store = TTLStore(maxsize=10, ttl=0.01)
    store.set("k", 1)
    time.sleep(0.03)
    assert store.get("k") is None


def test_ttl_store_survives_concurrent_writers_and_readers():
    store = TTLStore(maxsize=50, ttl=0.005)  # small and short-lived: constant eviction and expiry
    errors = []

    def hammer(seed):
        try:
            for i in range(2_000):
                key = (seed * i) % 200
                store.set(key, i)
                store.get(key)
        except Exception as e:  # pragma: no cover - only reached on failure
            errors.append(e)

    threads = [threading.Thread(target=hammer, args=(s,)) for s in range(1, 9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(store) <= 50
