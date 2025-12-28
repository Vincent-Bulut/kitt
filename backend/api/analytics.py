import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any, Tuple

import yfinance as yf
from cachetools import TTLCache

import utils

router = APIRouter(prefix='/analytics', tags=['ANALYTICS'])


PERIODS = ["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]
Period = Literal["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]

PERIODS_RET = ["ARITH"]
ReturnType = Literal["ARITH"]

# Cache 10 minutes (clé = ticker + asof + auto_adjust)
CACHE = TTLCache(maxsize=5000, ttl=600)

# =========================================================
# Pydantic models
# =========================================================

class YahooPerfRow(BaseModel):
    ticker: str
    asof_requested: Optional[str]
    asof_used: str
    last: float
    perf: Dict[Period, Optional[float]]


class YahooPerfResponse(BaseModel):
    data: List[YahooPerfRow]
    errors: Dict[str, str] = Field(default_factory=dict)


class YahooPerfRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=500)
    asof: Optional[str] = None
    auto_adjust: bool = True

class YahooReturnRow(BaseModel):
    ticker: str
    start_date_requested: str
    end_date_requested: str
    start_date_used: str
    end_date_used: str
    start_price: float
    end_price: float
    arithmetic_return: float  # percent


class YahooReturnResponse(BaseModel):
    data: List[YahooReturnRow]
    errors: Dict[str, str] = Field(default_factory=dict)


class YahooReturnRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=500)
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    auto_adjust: bool = True

class CumReturnPoint(BaseModel):
    date: str               # YYYY-MM-DD
    cum_return: float       # decimal (e.g. 0.123 = +12.3%)

class YahooCumReturnsSeries(BaseModel):
    ticker: str
    start_date_requested: str
    end_date_requested: str
    start_date_used: str
    base_price: float
    points: List[CumReturnPoint]

class YahooCumReturnsResponse(BaseModel):
    data: List[YahooCumReturnsSeries]
    errors: Dict[str, str] = Field(default_factory=dict)

class YahooCumReturnsRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=200)  # séries => limite plus basse
    start_date: str
    end_date: str
    auto_adjust: bool = True

# =========================================================
# Internal helpers
# =========================================================

def _nearest_prev_close(close: pd.Series, target_date: pd.Timestamp):
    s = close.loc[:target_date]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1]


def yahoo_perf_asof(
    ticker: str,
    asof: Optional[str] = None,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """
    Compute Yahoo Finance performance table as-of a given date.
    """

    cache_key = (ticker, str(asof), auto_adjust)
    if cache_key in CACHE:
        return CACHE[cache_key]

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
        last_price, last_date = _nearest_prev_close(close, asof_ts)
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
        past_price, _ = _nearest_prev_close(close, d)
        out[k] = None if past_price in (None, 0) else (last_price / past_price - 1) * 100

    df = pd.DataFrame([out])
    CACHE[cache_key] = df
    return df


def df_to_rows(df: pd.DataFrame) -> List[dict]:
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


# =========================================================
# Shared implementation
# =========================================================

def _run_perf(
    tickers: List[str],
    asof: Optional[str],
    auto_adjust: bool,
    format: str,
):
    data: List[dict] = []
    errors: Dict[str, str] = {}

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


# =========================================================
# Routes
# =========================================================

@router.get("/yahoo/perf", response_model=YahooPerfResponse)
def yahoo_perf_get(
    tickers: str = Query(..., description="Comma-separated: AAPL,SPY,AIR.PA"),
    asof: Optional[str] = Query(None, description="YYYY-MM-DD"),
    auto_adjust: bool = True,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="tickers is required")

    return _run_perf(ticker_list, asof, auto_adjust, format)


@router.post("/yahoo/perf-table", response_model=YahooPerfResponse)
def yahoo_perf_post(
    req: YahooPerfRequest,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    return _run_perf(req.tickers, req.asof, req.auto_adjust, format)

def _nearest_prev_close_on_or_before(close: pd.Series, target_date: pd.Timestamp):
    """
    Returns (price, date) for the last available close <= target_date.
    """
    s = close.loc[:target_date]
    if s.empty:
        return None, None
    price = float(s.iloc[-1].item()) if hasattr(s.iloc[-1], "item") else float(s.iloc[-1])
    return price, s.index[-1]


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
    if cache_key in CACHE:
        return CACHE[cache_key]

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

    start_price, start_used = _nearest_prev_close_on_or_before(close, start_ts)
    if start_price is None:
        raise ValueError(f"No price data on or before {start_ts.date()}")

    end_price, end_used = _nearest_prev_close_on_or_before(close, end_ts)
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
    CACHE[cache_key] = df
    return df


def df_to_return_rows(df: pd.DataFrame) -> List[dict]:
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


def _run_arithmetic_return(
    tickers: List[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    format: str,
):
    data: List[dict] = []
    errors: Dict[str, str] = {}

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


# =========================================================
# Routes: arithmetic return
# =========================================================

@router.get("/yahoo/arithmetic-return", response_model=YahooReturnResponse)
def yahoo_arithmetic_return_get(
    tickers: str = Query(..., description="Comma-separated: AAPL,SPY,AIR.PA"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    auto_adjust: bool = True,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="tickers is required")

    return _run_arithmetic_return(ticker_list, start_date, end_date, auto_adjust, format)


@router.post("/yahoo/arithmetic-return", response_model=YahooReturnResponse)
def yahoo_arithmetic_return_post(
    req: YahooReturnRequest,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    return _run_arithmetic_return(req.tickers, req.start_date, req.end_date, req.auto_adjust, format)

def _download_prices_close(
    tickers: List[str],
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    auto_adjust: bool,
) -> pd.DataFrame:
    """
    Télécharge les prix Close (auto_adjust => adj close économique) pour plusieurs tickers.
    Retourne DataFrame index date, colonnes tickers.
    """
    fetch_start = (start_ts - pd.Timedelta(days=10)).date().isoformat()
    fetch_end = (end_ts + pd.Timedelta(days=1)).date().isoformat()

    df = yf.download(
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
    # On essaie d'extraire "Close" de manière robuste.
    if isinstance(df.columns, pd.MultiIndex):
        # Cas le plus fréquent: niveau 0 = price field ("Close", "Open"...), niveau 1 = ticker
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

    # Tronque proprement la fenêtre demandée (on garde les dates <= end_ts)
    close = close.loc[:end_ts]
    return close


def _nearest_prev_price(series: pd.Series, target: pd.Timestamp) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
    s = series.loc[:target].dropna()
    if s.empty:
        return None, None
    price = float(s.iloc[-1].item()) if hasattr(s.iloc[-1], "item") else float(s.iloc[-1])
    return price, s.index[-1]


def cumulative_returns_series_from_prices(
    prices: pd.Series,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp
) -> Tuple[pd.Timestamp, float, pd.Series]:
    """
    Renvoie (start_used_date, base_price, cum_return_series_decimal)
    cum_return_series est indexé par date, valeurs en décimal (0.10 = +10%).
    """
    s = prices.dropna().copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s = s.loc[:end_ts]

    base_price, start_used = _nearest_prev_price(s, start_ts)
    if base_price is None:
        raise ValueError(f"No price data on or before {start_ts.date()}")

    # Garder à partir du start_used (cohérence)
    s2 = s.loc[start_used:]
    if s2.empty:
        raise ValueError("No prices after start_date_used")

    cum = (s2 / base_price) - 1.0
    return start_used, float(base_price), cum


def _run_cum_returns(
    tickers: List[str],
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
    close_df = _download_prices_close(tickers, start_ts, end_ts, auto_adjust=auto_adjust)
    if close_df.empty:
        raise ValueError("No data returned by Yahoo for requested tickers/date range")

    data: List[dict] = []
    errors: Dict[str, str] = {}

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


# =========================================================
# Routes: cumulative returns series
# =========================================================

@router.get("/yahoo/cumulative-returns", response_model=YahooCumReturnsResponse)
def yahoo_cumulative_returns_get(
    tickers: str = Query(..., description="Comma-separated: AAPL,SPY,AIR.PA"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    auto_adjust: bool = True,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="tickers is required")

    return _run_cum_returns(ticker_list, start_date, end_date, auto_adjust, format)


@router.post("/yahoo/cumulative-returns", response_model=YahooCumReturnsResponse)
def yahoo_cumulative_returns_post(
    req: YahooCumReturnsRequest,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    return _run_cum_returns(req.tickers, req.start_date, req.end_date, req.auto_adjust, format)