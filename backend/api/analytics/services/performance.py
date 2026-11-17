"""Performance analytics: period returns, cumulative returns, drawdowns and volatility."""

import io
from typing import Any

import pandas as pd
import yfinance as yf
from cachetools import TTLCache
from fastapi.responses import StreamingResponse

from backend.api import utils
from backend.api.analytics.market_data import download_close_multi, download_close_multi_interval, download_prices_close
from backend.api.analytics.quant.drawdown import drawdown_metrics_and_episodes, drawdown_series, max_drawdown_path
from backend.api.analytics.quant.returns import (
    compute_vols,
    cumulative_returns_series_from_prices,
    nearest_prev_price,
)
from backend.api.analytics.schemas import PERIODS, ReturnMode, VolFrequency

# 10-minute caches (key = tickers + dates + parameters)
PERF_CACHE = TTLCache(maxsize=5000, ttl=600)
DRAWDOWN_CACHE = TTLCache(maxsize=2000, ttl=600)

ANNVOL_CACHE = TTLCache(maxsize=2000, ttl=600)


def yahoo_perf_asof(
    ticker: str,
    asof: str | None = None,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """
    Compute Yahoo Finance performance table as-of a given date.
    """

    cache_key = (ticker, str(asof), auto_adjust)
    if cache_key in PERF_CACHE:
        return PERF_CACHE[cache_key]

    t = yf.Ticker(ticker)
    hist = t.history(period="10y", interval="1d", auto_adjust=auto_adjust)

    if hist.empty:
        raise ValueError(f"No data for ticker '{ticker}'")

    close = hist["Close"].dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)

    asof_ts = utils.convert_to_timestamp(asof)

    # Last close <= asof
    if asof_ts is None:
        last_price = float(close.iloc[-1])
        last_date = close.index[-1]
    else:
        last_price, last_date = nearest_prev_price(close, asof_ts)
        if last_price is None:
            raise ValueError(f"No data on or before {asof_ts.date()}")

    targets = {
        "1D": last_date - pd.Timedelta(days=1),
        "1W": last_date - pd.Timedelta(days=7),
        "1M": last_date - pd.Timedelta(days=30),
        "YTD": pd.Timestamp(year=last_date.year, month=1, day=1),
        "1Y": last_date - pd.Timedelta(days=365),
        "3Y": last_date - pd.Timedelta(days=365 * 3),
        "5Y": last_date - pd.Timedelta(days=365 * 5),
    }

    out = {
        "Ticker": ticker,
        "AsOfRequested": None if asof_ts is None else asof_ts.date(),
        "AsOfUsed": last_date.date(),
        "Last": last_price,
    }

    for k, d in targets.items():
        past_price, _ = nearest_prev_price(close, d)
        out[k] = None if past_price in (None, 0) else (last_price / past_price - 1) * 100

    df = pd.DataFrame([out])
    PERF_CACHE[cache_key] = df
    return df


def df_to_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "ticker": r["Ticker"],
            "asof_requested": None if pd.isna(r["AsOfRequested"]) else str(r["AsOfRequested"]),
            "asof_used": str(r["AsOfUsed"]),
            "last": float(r["Last"]),
            "perf": {p: (None if pd.isna(r[p]) else float(r[p])) for p in PERIODS},
        })
    return rows


def run_perf(
    tickers: list[str],
    asof: str | None,
    auto_adjust: bool,
    format: str,
):
    data: list[dict] = []
    errors: dict[str, str] = {}

    for ticker in tickers:
        try:
            df = yahoo_perf_asof(ticker, asof=asof, auto_adjust=auto_adjust)
            data.extend(df_to_rows(df))
        except Exception as e:
            errors[ticker] = str(e)

    if format == "csv":
        flat = []
        for r in data:
            row = {
                "ticker": r["ticker"],
                "asof_requested": r["asof_requested"],
                "asof_used": r["asof_used"],
                "last": r["last"],
            }
            row.update(r["perf"])
            flat.append(row)

        df = pd.DataFrame(flat)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=yahoo_perf.csv"},
        )

    return {"data": data, "errors": errors}


def yahoo_arithmetic_return(
    ticker: str,
    start_date: str,
    end_date: str,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """
    Compute arithmetic return between start_date and end_date (inclusive logic by nearest previous close).
    """
    cache_key = ("arith_ret", ticker, start_date, end_date, auto_adjust)
    if cache_key in PERF_CACHE:
        return PERF_CACHE[cache_key]

    # Parse dates
    start_ts = utils.convert_to_timestamp(start_date)
    end_ts = utils.convert_to_timestamp(end_date)
    if start_ts is None or end_ts is None:
        raise ValueError("start_date and end_date must be valid dates (YYYY-MM-DD)")
    if end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    t = yf.Ticker(ticker)

    # Fetch a bit wider window to be safe around non-trading days / holidays
    fetch_start = (start_ts - pd.Timedelta(days=10)).date().isoformat()
    fetch_end = (end_ts + pd.Timedelta(days=3)).date().isoformat()

    hist = t.history(
        start=fetch_start,
        end=fetch_end,
        interval="1d",
        auto_adjust=auto_adjust
    )

    if hist.empty:
        raise ValueError(f"No data for ticker '{ticker}'")

    close = hist["Close"].dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)

    start_price, start_used = nearest_prev_price(close, start_ts)
    if start_price is None:
        raise ValueError(f"No price data on or before {start_ts.date()}")

    end_price, end_used = nearest_prev_price(close, end_ts)
    if end_price is None:
        raise ValueError(f"No price data on or before {end_ts.date()}")

    if start_price == 0:
        raise ValueError("Start price is 0, cannot compute return")

    ar = (end_price / start_price - 1.0) * 100.0

    out = {
        "Ticker": ticker,
        "StartDateRequested": start_ts.date(),
        "EndDateRequested": end_ts.date(),
        "StartDateUsed": start_used.date(),
        "EndDateUsed": end_used.date(),
        "StartPrice": float(start_price),
        "EndPrice": float(end_price),
        "ArithmeticReturn": float(ar),
    }

    df = pd.DataFrame([out])
    PERF_CACHE[cache_key] = df
    return df


def df_to_return_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "ticker": r["Ticker"],
            "start_date_requested": str(r["StartDateRequested"]),
            "end_date_requested": str(r["EndDateRequested"]),
            "start_date_used": str(r["StartDateUsed"]),
            "end_date_used": str(r["EndDateUsed"]),
            "start_price": float(r["StartPrice"]),
            "end_price": float(r["EndPrice"]),
            "arithmetic_return": float(r["ArithmeticReturn"]),
        })
    return rows


def run_arithmetic_return(
    tickers: list[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    format: str,
):
    data: list[dict] = []
    errors: dict[str, str] = {}

    for ticker in tickers:
        try:
            df = yahoo_arithmetic_return(
                ticker,
                start_date=start_date,
                end_date=end_date,
                auto_adjust=auto_adjust
            )
            data.extend(df_to_return_rows(df))
        except Exception as e:
            errors[ticker] = str(e)

    if format == "csv":
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=yahoo_arithmetic_return.csv"},
        )

    return {"data": data, "errors": errors}


def run_cum_returns(
    tickers: list[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    format: str,
):
    start_ts = utils.convert_to_timestamp(start_date)
    end_ts = utils.convert_to_timestamp(end_date)
    if start_ts is None or end_ts is None:
        raise ValueError("start_date and end_date must be valid dates (YYYY-MM-DD)")
    if end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    # Download multi-tickers once
    close_df = download_prices_close(tickers, start_ts, end_ts, auto_adjust=auto_adjust)
    if close_df.empty:
        raise ValueError("No data returned by Yahoo for requested tickers/date range")

    data: list[dict] = []
    errors: dict[str, str] = {}

    for ticker in tickers:
        try:
            if ticker not in close_df.columns:
                raise ValueError("Ticker not present in downloaded data")

            start_used, base_price, cum = cumulative_returns_series_from_prices(
                close_df[ticker],
                start_ts=start_ts,
                end_ts=end_ts
            )

            points = [
                {"date": d.strftime("%Y-%m-%d"), "cum_return": float(v)}
                for d, v in cum.items()
            ]

            data.append({
                "ticker": ticker,
                "start_date_requested": start_ts.date().isoformat(),
                "end_date_requested": end_ts.date().isoformat(),
                "start_date_used": start_used.date().isoformat(),
                "base_price": float(base_price),
                "points": points
            })
        except Exception as e:
            errors[ticker] = str(e)

    if format == "csv":
        # format long: date,ticker,cum_return
        flat = []
        for s in data:
            for pt in s["points"]:
                flat.append({"date": pt["date"], "ticker": s["ticker"], "cum_return": pt["cum_return"]})
        df = pd.DataFrame(flat)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=yahoo_cum_returns.csv"},
        )

    return {"data": data, "errors": errors}


def _serialize_dd_series(dd_df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for idx, row in dd_df.iterrows():
        out.append({
            "date": idx.date().isoformat(),
            "price": float(row["Price"]),
            "running_max": float(row["RunningMax"]),
            "drawdown": float(row["Drawdown"]),
        })
    return out


def run_drawdown(
    tickers: list[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    include_series: bool,
) -> dict[str, Any]:
    start_ts = utils.convert_to_timestamp(start_date)
    end_ts = utils.convert_to_timestamp(end_date)
    if start_ts is None or end_ts is None:
        raise ValueError("start_date and end_date must be valid dates (YYYY-MM-DD)")
    if end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    cache_key = ("dd_multi", tuple(tickers), start_date, end_date, auto_adjust, include_series)
    if cache_key in DRAWDOWN_CACHE:
        return DRAWDOWN_CACHE[cache_key]

    close = download_close_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    data = []
    errors: dict[str, str] = {}

    for t in tickers:
        try:
            if t not in close.columns:
                raise ValueError("Ticker not found in downloaded data")

            s = close[t].dropna()
            if s.empty or len(s) < 5:
                raise ValueError("Not enough points in window")

            metrics, episodes = drawdown_metrics_and_episodes(s)
            path = max_drawdown_path(s)

            row = {
                "ticker": t,
                "start_date_requested": start_ts.date().isoformat(),
                "end_date_requested": end_ts.date().isoformat(),
                "metrics": metrics,
                "path": path,
                "episodes": episodes,
            }

            if include_series:
                dd_df = drawdown_series(s)
                row["series"] = _serialize_dd_series(dd_df)

            data.append(row)

        except Exception as e:
            errors[t] = str(e)

    out = {"data": data, "errors": errors}
    DRAWDOWN_CACHE[cache_key] = out
    return out


def run_annualized_volatility(
    tickers: list[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    frequency: VolFrequency,
    return_mode: ReturnMode,
) -> dict[str, Any]:
    start_ts = utils.convert_to_timestamp(start_date)
    end_ts = utils.convert_to_timestamp(end_date)

    if start_ts is None or end_ts is None:
        raise ValueError("start_date and end_date must be valid dates (YYYY-MM-DD)")
    if end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    cache_key = ("ann_vol", tuple(tickers), start_date, end_date, auto_adjust, frequency, return_mode)
    if cache_key in ANNVOL_CACHE:
        return ANNVOL_CACHE[cache_key]

    close = download_close_multi_interval(tickers, start_ts, end_ts, auto_adjust, frequency)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    data: list[dict] = []
    errors: dict[str, str] = {}

    for t in tickers:
        try:
            if t not in close.columns:
                raise ValueError("Ticker not found in downloaded data")

            res = compute_vols(
                close[t],
                start_ts=start_ts,
                end_ts=end_ts,
                frequency=frequency,
                return_mode=return_mode,
            )

            data.append({
                "ticker": t,
                "start_date_requested": start_ts.date().isoformat(),
                "end_date_requested": end_ts.date().isoformat(),
                "start_date_used": res["start_used"].date().isoformat(),
                "end_date_used": res["end_used"].date().isoformat(),
                "observations": int(res["observations"]),

                "volatility_period": float(res["volatility_period"]),
                "annualized_volatility": float(res["annualized_volatility"]),

                "frequency": frequency,
                "price_type": "Adjusted Close" if auto_adjust else "Close",
                "return_mode": return_mode,
            })

        except Exception as e:
            errors[t] = str(e)

    out = {"data": data, "errors": errors}
    ANNVOL_CACHE[cache_key] = out
    return out
