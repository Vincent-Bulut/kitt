import io
import pandas as pd
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any, Tuple
from scipy.stats import norm

import yfinance as yf
from cachetools import TTLCache

from backend.api import utils

router = APIRouter(prefix='/analytics', tags=['ANALYTICS'])


PERIODS = ["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]
Period = Literal["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]

PERIODS_RET = ["ARITH"]
ReturnType = Literal["ARITH"]

# Cache 10 minutes (clé = ticker + asof + auto_adjust)
CACHE = TTLCache(maxsize=5000, ttl=600)
DRAWDOWN_CACHE = TTLCache(maxsize=2000, ttl=600)

VolFrequency = Literal["daily", "weekly", "monthly"]
ReturnMode = Literal["log", "arith"]

ANNVOL_CACHE = TTLCache(maxsize=2000, ttl=600)

_ANNUALIZATION = {
    "daily": 252.0,
    "weekly": 52.0,
    "monthly": 12.0,
}

_INTERVAL_MAP = {
    "daily": "1d",
    "weekly": "1wk",
    "monthly": "1mo",
}

RISK_CACHE = TTLCache(maxsize=2000, ttl=600)

MC_CACHE = TTLCache(maxsize=500, ttl=600)

_PERIOD_DAYS = {
    "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "2Y": 730, "3Y": 1095,
    "5Y": 1825, "10Y": 3650,
}


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

class DrawdownEpisode(BaseModel):
    start_date: str
    trough_date: str
    end_date: Optional[str]
    duration_days: int
    max_drawdown: float

class DrawdownMetrics(BaseModel):
    observations: int
    max_drawdown: float
    current_drawdown: float
    num_drawdown_episodes: int
    avg_drawdown_length_trading_days: float
    max_drawdown_length_trading_days: int
    worst_episode_trough: float

class DrawdownPath(BaseModel):
    peak_date: str
    trough_date: str
    recovery_date: Optional[str]
    max_drawdown: float

class DrawdownPoint(BaseModel):
    date: str
    price: float
    running_max: float
    drawdown: float

class YahooDrawdownRow(BaseModel):
    ticker: str
    start_date_requested: str
    end_date_requested: str
    metrics: DrawdownMetrics
    path: DrawdownPath
    episodes: List[DrawdownEpisode] = Field(default_factory=list)
    series: Optional[List[DrawdownPoint]] = None

class YahooDrawdownResponse(BaseModel):
    data: List[YahooDrawdownRow]
    errors: Dict[str, str] = Field(default_factory=dict)

class YahooDrawdownRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=200)
    start_date: str
    end_date: str
    auto_adjust: bool = True
    include_series: bool = False

class YahooAnnVolRow(BaseModel):
    ticker: str
    start_date_requested: str
    end_date_requested: str
    start_date_used: str
    end_date_used: str
    observations: int

    volatility_period: float          # std(returns) on the window (NOT annualized)
    annualized_volatility: float      # volatility_period * sqrt(252/52/12)

    frequency: VolFrequency
    price_type: str                   # "Adjusted Close" or "Close"
    return_mode: ReturnMode           # "log" or "arith"


class YahooAnnVolResponse(BaseModel):
    data: List[YahooAnnVolRow]
    errors: Dict[str, str] = Field(default_factory=dict)


class YahooAnnVolRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=200)
    start_date: str
    end_date: str
    auto_adjust: bool = True
    frequency: VolFrequency = "daily"
    return_mode: ReturnMode = "log"

class VaREsPoint(BaseModel):
    confidence_level: float
    var_historical: float
    es_historical: float
    var_gaussian: float
    es_gaussian: float
    var_cornish_fisher: float
    es_cf_empirical_tail: float


class YahooVaREsRow(BaseModel):
    ticker: str
    start_date_requested: str
    end_date_requested: str
    start_date_used: str
    end_date_used: str
    observations: int
    return_mode: ReturnMode
    horizon: str = "1D"
    price_type: str  # "Adjusted Close" or "Close"
    points: List[VaREsPoint]


class YahooVaREsResponse(BaseModel):
    data: List[YahooVaREsRow]
    errors: Dict[str, str] = Field(default_factory=dict)


class YahooVaREsRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=200)
    start_date: str
    end_date: str
    auto_adjust: bool = True
    return_mode: ReturnMode = "arith"
    confidence_levels: List[float] = Field(default_factory=lambda: [0.95, 0.99])


class YahooAllMetricsResponse(BaseModel):
    perf: Optional[YahooPerfResponse] = None
    vol: Optional[YahooAnnVolResponse] = None
    dd: Optional[YahooDrawdownResponse] = None
    risk: Optional[YahooVaREsResponse] = None
    cum_returns: Optional[YahooCumReturnsResponse] = None


class MonteCarloPercentiles(BaseModel):
    p5: List[float]
    p25: List[float]
    p50: List[float]
    p75: List[float]
    p95: List[float]


class MonteCarloStats(BaseModel):
    n_simulations: int
    horizon_days: int
    lookback_start: str
    lookback_end: str
    initial_value: float
    expected_final: float
    p5_final: float
    p25_final: float
    p50_final: float
    p75_final: float
    p95_final: float
    annualized_drift: float
    annualized_volatility: float
    prob_positive: float


class MonteCarloResponse(BaseModel):
    dates: List[str]
    percentiles: MonteCarloPercentiles
    samples: List[List[float]]
    stats: MonteCarloStats
    tickers: List[str]
    weights: List[float]
    errors: Dict[str, str] = Field(default_factory=dict)


class MonteCarloRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=100)
    weights: List[float] = Field(min_length=1, max_length=100)
    horizon_days: int = Field(default=252, ge=10, le=2520)
    n_simulations: int = Field(default=1000, ge=50, le=20000)
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    seed: int = 42
    n_sample_paths: int = Field(default=30, ge=0, le=200)
    initial_value: float = Field(default=1.0, gt=0)


class YahooAllMetricsRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=200)
    asof: Optional[str] = None
    period: str = "3Y"  # Default to 3 years
    auto_adjust: bool = True
    frequency: VolFrequency = "daily"
    confidence_levels: str = "0.95"

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

# =========================================================
# Helpers
# =========================================================

def _download_close_multi(
    tickers: List[str],
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    auto_adjust: bool,
) -> pd.DataFrame:
    df = yf.download(
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


def _drawdown_series(prices: pd.Series) -> pd.DataFrame:
    p = prices.dropna().copy()
    p.index = pd.to_datetime(p.index).tz_localize(None)
    rm = p.cummax()
    dd = p / rm - 1.0
    return pd.DataFrame({"Price": p, "RunningMax": rm, "Drawdown": dd})


def _drawdown_metrics_and_episodes(prices: pd.Series) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    dd_df = _drawdown_series(prices)
    dd = dd_df["Drawdown"]

    max_dd = float(dd.min())
    current_dd = float(dd.iloc[-1].item())

    in_dd = dd < 0
    episode_id = (in_dd != in_dd.shift(1, fill_value=False)).cumsum()

    durations = []
    troughs = []
    episodes = []
    for _, block in dd_df[in_dd].groupby(episode_id[in_dd]):
        durations.append(int(len(block)))
        trough_val = float(block["Drawdown"].min())
        troughs.append(trough_val)
        
        trough_dt = block["Drawdown"].idxmin()
        start_dt = block.index[0]
        end_dt = block.index[-1]
        
        # Check if it's recovered (last point drawdown is 0 or it's the end of series)
        # In this loop we only have blocks where in_dd is True. 
        # If the block ends before the end of the full series, it means it recovered.
        recovered = end_dt < dd.index[-1]
        
        episodes.append({
            "start_date": start_dt.date().isoformat(),
            "trough_date": trough_dt.date().isoformat(),
            "end_date": end_dt.date().isoformat() if recovered else None,
            "duration_days": int(len(block)),
            "max_drawdown": trough_val
        })

    metrics = {
        "observations": int(dd.dropna().shape[0]),
        "max_drawdown": max_dd,
        "current_drawdown": current_dd,
        "num_drawdown_episodes": int(len(durations)),
        "avg_drawdown_length_trading_days": float(np.mean(durations)) if durations else 0.0,
        "max_drawdown_length_trading_days": int(max(durations)) if durations else 0,
        "worst_episode_trough": float(min(troughs)) if troughs else 0.0,
    }
    return metrics, episodes


def _max_drawdown_path(prices: pd.Series) -> Dict[str, Any]:
    dd_df = _drawdown_series(prices)
    p = dd_df["Price"]
    dd = dd_df["Drawdown"]

    trough_dt = dd.idxmin()
    trough_dd = float(dd.loc[trough_dt])

    peak_dt = p.loc[:trough_dt].idxmax()
    peak_price = float(p.loc[peak_dt].item())

    after = p.loc[trough_dt:]
    rec = after[after >= peak_price]
    rec_dt = rec.index[0] if not rec.empty else None

    return {
        "peak_date": peak_dt.date().isoformat(),
        "trough_date": trough_dt.date().isoformat(),
        "recovery_date": None if rec_dt is None else rec_dt.date().isoformat(),
        "max_drawdown": trough_dd,
    }


def _serialize_dd_series(dd_df: pd.DataFrame) -> List[Dict[str, Any]]:
    out = []
    for idx, row in dd_df.iterrows():
        out.append({
            "date": idx.date().isoformat(),
            "price": float(row["Price"]),
            "running_max": float(row["RunningMax"]),
            "drawdown": float(row["Drawdown"]),
        })
    return out


def _run_drawdown(
    tickers: List[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    include_series: bool,
) -> Dict[str, Any]:
    start_ts = utils.convert_to_timestamp(start_date)
    end_ts = utils.convert_to_timestamp(end_date)
    if start_ts is None or end_ts is None:
        raise ValueError("start_date and end_date must be valid dates (YYYY-MM-DD)")
    if end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    cache_key = ("dd_multi", tuple(tickers), start_date, end_date, auto_adjust, include_series)
    if cache_key in DRAWDOWN_CACHE:
        return DRAWDOWN_CACHE[cache_key]

    close = _download_close_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    data = []
    errors: Dict[str, str] = {}

    for t in tickers:
        try:
            if t not in close.columns:
                raise ValueError("Ticker not found in downloaded data")

            s = close[t].dropna()
            if s.empty or len(s) < 5:
                raise ValueError("Not enough points in window")

            metrics, episodes = _drawdown_metrics_and_episodes(s)
            path = _max_drawdown_path(s)

            row = {
                "ticker": t,
                "start_date_requested": start_ts.date().isoformat(),
                "end_date_requested": end_ts.date().isoformat(),
                "metrics": metrics,
                "path": path,
                "episodes": episodes,
            }

            if include_series:
                dd_df = _drawdown_series(s)
                row["series"] = _serialize_dd_series(dd_df)

            data.append(row)

        except Exception as e:
            errors[t] = str(e)

    out = {"data": data, "errors": errors}
    DRAWDOWN_CACHE[cache_key] = out
    return out


# =========================================================
# Routes
# =========================================================

@router.get("/yahoo/drawdowns", response_model=YahooDrawdownResponse)
def yahoo_drawdowns_get(
    tickers: str = Query(..., description="Comma-separated: AAPL,SPY,AIR.PA"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    auto_adjust: bool = True,
    include_series: bool = False,
):
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="tickers is required")

    return _run_drawdown(ticker_list, start_date, end_date, auto_adjust, include_series)


@router.post("/yahoo/drawdowns", response_model=YahooDrawdownResponse)
def yahoo_drawdowns_post(req: YahooDrawdownRequest):
    return _run_drawdown(req.tickers, req.start_date, req.end_date, req.auto_adjust, req.include_series)

# =========================
# Helpers
# =========================

def _nearest_prev_price(series: pd.Series, target: pd.Timestamp) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
    """
    Returns (price, date) for the last available price <= target.
    """
    s = series.loc[:target].dropna()
    if s.empty:
        return None, None
    v = s.iloc[-1]
    price = float(v.item()) if hasattr(v, "item") else float(v)
    return price, s.index[-1]


def _download_close_multi_interval(
    tickers: List[str],
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

    df = yf.download(
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


def _compute_vols(
    prices: pd.Series,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    frequency: VolFrequency,
    return_mode: ReturnMode,
) -> Dict[str, Any]:
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
    _, start_used = _nearest_prev_price(s, start_ts)
    if start_used is None:
        raise ValueError(f"No price data on or before {start_ts.date()}")

    _, end_used = _nearest_prev_price(s, end_ts)
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


def _run_annualized_volatility(
    tickers: List[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    frequency: VolFrequency,
    return_mode: ReturnMode,
) -> Dict[str, Any]:
    start_ts = utils.convert_to_timestamp(start_date)
    end_ts = utils.convert_to_timestamp(end_date)

    if start_ts is None or end_ts is None:
        raise ValueError("start_date and end_date must be valid dates (YYYY-MM-DD)")
    if end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    cache_key = ("ann_vol", tuple(tickers), start_date, end_date, auto_adjust, frequency, return_mode)
    if cache_key in ANNVOL_CACHE:
        return ANNVOL_CACHE[cache_key]

    close = _download_close_multi_interval(tickers, start_ts, end_ts, auto_adjust, frequency)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    data: List[dict] = []
    errors: Dict[str, str] = {}

    for t in tickers:
        try:
            if t not in close.columns:
                raise ValueError("Ticker not found in downloaded data")

            res = _compute_vols(
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

# =========================
# Routes
# =========================

@router.get("/yahoo/annualized-volatility", response_model=YahooAnnVolResponse)
def yahoo_annualized_volatility_get(
    tickers: str = Query(..., description="Comma-separated: AAPL,SPY,AIR.PA"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    auto_adjust: bool = True,
    frequency: VolFrequency = Query("daily", description="daily|weekly|monthly"),
    return_mode: ReturnMode = Query("log", description="log|arith"),
):
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="tickers is required")

    return _run_annualized_volatility(
        tickers=ticker_list,
        start_date=start_date,
        end_date=end_date,
        auto_adjust=auto_adjust,
        frequency=frequency,
        return_mode=return_mode,
    )


@router.post("/yahoo/annualized-volatility", response_model=YahooAnnVolResponse)
def yahoo_annualized_volatility_post(req: YahooAnnVolRequest):
    return _run_annualized_volatility(
        tickers=req.tickers,
        start_date=req.start_date,
        end_date=req.end_date,
        auto_adjust=req.auto_adjust,
        frequency=req.frequency,
        return_mode=req.return_mode,
    )

# =========================
# Helpers (download + dates)
# =========================

def _nearest_prev_price(series: pd.Series, target: pd.Timestamp) -> Tuple[Optional[float], Optional[pd.Timestamp]]:
    s = series.loc[:target].dropna()
    if s.empty:
        return None, None
    v = s.iloc[-1]
    price = float(v.item()) if hasattr(v, "item") else float(v)
    return price, s.index[-1]


def _download_close_daily_multi(
    tickers: List[str],
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

    df = yf.download(
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

# =========================
# Risk math (VaR / ES)
# =========================

def _as_return_series(returns: pd.Series) -> pd.Series:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    return r

def var_historical(returns: pd.Series, alpha: float) -> float:
    r = _as_return_series(returns).to_numpy()
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1 - alpha)   # left tail threshold in return space
    return float(-q)                # loss positive

def es_historical(returns: pd.Series, alpha: float) -> float:
    r = _as_return_series(returns).to_numpy()
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1 - alpha)
    tail = r[r <= q]
    return float(-np.mean(tail)) if tail.size else 0.0

def var_gaussian(returns: pd.Series, alpha: float) -> float:
    r = _as_return_series(returns)
    if r.empty or len(r) < 2:
        return 0.0
    mu = float(r.mean())
    sigma = float(r.std(ddof=1))
    if sigma == 0:
        return 0.0
    z_left = float(norm.ppf(1 - alpha))  # negative
    var_return = mu + sigma * z_left
    return float(-var_return)

def es_gaussian(returns: pd.Series, alpha: float) -> float:
    r = _as_return_series(returns)
    if r.empty or len(r) < 2:
        return 0.0
    mu = float(r.mean())
    sigma = float(r.std(ddof=1))
    if sigma == 0:
        return 0.0
    z_left = float(norm.ppf(1 - alpha))
    phi = float(norm.pdf(z_left))
    es_return = mu - sigma * (phi / (1 - alpha))  # left-tail ES in return space
    return float(-es_return)

def var_cornish_fisher(returns: pd.Series, alpha: float) -> float:
    """
    Cornish-Fisher adjusted VaR under non-normality using skew/kurt.
    VaR returned as positive loss.
    """
    r = _as_return_series(returns)
    if r.empty or len(r) < 5:
        return 0.0

    mu = float(r.mean())
    sigma = float(r.std(ddof=1))
    if sigma == 0:
        return 0.0

    # sample skewness and excess kurtosis
    s = float(r.skew())
    k_excess = float(r.kurtosis())  # pandas = excess kurtosis by default

    z = float(norm.ppf(1 - alpha))  # negative (left tail)
    z2 = z * z
    z3 = z2 * z

    # Cornish-Fisher expansion
    z_cf = (
        z
        + (1/6) * (z2 - 1) * s
        + (1/24) * (z3 - 3*z) * k_excess
        - (1/36) * (2*z3 - 5*z) * (s**2)
    )

    var_return = mu + sigma * z_cf
    return float(-var_return)

def es_cf_empirical_tail(returns: pd.Series, alpha: float) -> float:
    """
    Practical: CF VaR threshold, then empirical mean of returns <= threshold.
    """
    r = _as_return_series(returns).to_numpy()
    if r.size == 0:
        return 0.0

    var_cf_loss = var_cornish_fisher(pd.Series(r), alpha)  # positive loss
    threshold_return = -var_cf_loss                         # return threshold (negative)

    tail = r[r <= threshold_return]
    return float(-np.mean(tail)) if tail.size else 0.0

def es_summary(returns: pd.Series, confidence_levels: List[float]) -> List[Dict[str, Any]]:
    out = []
    for alpha in confidence_levels:
        out.append({
            "confidence_level": float(alpha),
            "var_historical": var_historical(returns, alpha),
            "es_historical": es_historical(returns, alpha),
            "var_gaussian": var_gaussian(returns, alpha),
            "es_gaussian": es_gaussian(returns, alpha),
            "var_cornish_fisher": var_cornish_fisher(returns, alpha),
            "es_cf_empirical_tail": es_cf_empirical_tail(returns, alpha),
        })
    return out

# =========================
# Core runner
# =========================

def _run_var_es(
    tickers: List[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    return_mode: ReturnMode,
    confidence_levels: List[float],
) -> Dict[str, Any]:
    start_ts = utils.convert_to_timestamp(start_date)
    end_ts = utils.convert_to_timestamp(end_date)
    if start_ts is None or end_ts is None:
        raise ValueError("start_date and end_date must be valid dates (YYYY-MM-DD)")
    if end_ts < start_ts:
        raise ValueError("end_date must be >= start_date")

    # validate confidence levels
    cls = []
    for a in confidence_levels:
        if not (0.5 < float(a) < 1.0):
            raise ValueError("confidence_levels must be in (0.5, 1.0)")
        cls.append(float(a))

    cache_key = ("var_es", tuple(tickers), start_date, end_date, auto_adjust, return_mode, tuple(cls))
    if cache_key in RISK_CACHE:
        return RISK_CACHE[cache_key]

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    data: List[dict] = []
    errors: Dict[str, str] = {}

    for t in tickers:
        try:
            if t not in close.columns:
                raise ValueError("Ticker not found in downloaded data")

            s = close[t].dropna()
            if s.empty:
                raise ValueError("No close prices for ticker in window")

            # find start/end used (nearest <= requested)
            _, start_used = _nearest_prev_price(s, start_ts)
            if start_used is None:
                raise ValueError(f"No price data on or before {start_ts.date()}")

            _, end_used = _nearest_prev_price(s, end_ts)
            if end_used is None:
                raise ValueError(f"No price data on or before {end_ts.date()}")

            window_prices = s.loc[start_used:end_used].dropna()
            if len(window_prices) < 10:
                raise ValueError("Not enough price points in window")

            if return_mode == "log":
                returns = np.log(window_prices).diff()
            else:
                returns = window_prices.pct_change()

            returns = _as_return_series(returns)
            if len(returns) < 10:
                raise ValueError("Not enough returns to compute risk metrics")

            points = es_summary(returns, cls)

            data.append({
                "ticker": t,
                "start_date_requested": start_ts.date().isoformat(),
                "end_date_requested": end_ts.date().isoformat(),
                "start_date_used": start_used.date().isoformat(),
                "end_date_used": end_used.date().isoformat(),
                "observations": int(len(returns)),
                "return_mode": return_mode,
                "horizon": "1D",
                "price_type": "Adjusted Close" if auto_adjust else "Close",
                "points": points,
            })

        except Exception as e:
            errors[t] = str(e)

    out = {"data": data, "errors": errors}
    RISK_CACHE[cache_key] = out
    return out

# =========================
# Routes
# =========================

@router.get("/yahoo/var-es", response_model=YahooVaREsResponse)
def yahoo_var_es_get(
    tickers: str = Query(..., description="Comma-separated: AAPL,SPY,AIR.PA"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    auto_adjust: bool = True,
    return_mode: ReturnMode = Query("arith", description="arith|log"),
    confidence_levels: str = Query("0.95,0.99", description="Comma-separated, e.g. 0.95,0.99"),
):
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="tickers is required")

    cl_list = [float(x.strip()) for x in confidence_levels.split(",") if x.strip()]

    return _run_var_es(
        tickers=ticker_list,
        start_date=start_date,
        end_date=end_date,
        auto_adjust=auto_adjust,
        return_mode=return_mode,
        confidence_levels=cl_list,
    )


@router.post("/yahoo/var-es", response_model=YahooVaREsResponse)
def yahoo_var_es_post(req: YahooVaREsRequest):
    return _run_var_es(
        tickers=req.tickers,
        start_date=req.start_date,
        end_date=req.end_date,
        auto_adjust=req.auto_adjust,
        return_mode=req.return_mode,
        confidence_levels=req.confidence_levels,
    )


@router.post("/yahoo/all-metrics", response_model=YahooAllMetricsResponse)
def yahoo_all_metrics_post(req: YahooAllMetricsRequest):
    # 1. Performance
    perf_data = _run_perf(
        tickers=req.tickers,
        asof=req.asof,
        auto_adjust=req.auto_adjust,
        format="json"
    )

    # Base date for other metrics: use asof or today
    asof_ts = utils.convert_to_timestamp(req.asof)
    if asof_ts is None:
        asof_ts = pd.Timestamp.now()
    
    end_date_str = asof_ts.date().isoformat()
    
    # Calculate start_date based on period
    period_map = {
        "1M": 30,
        "3M": 90,
        "6M": 180,
        "1Y": 365,
        "2Y": 365 * 2,
        "3Y": 365 * 3,
        "5Y": 365 * 5,
        "10Y": 365 * 10,
    }
    
    days = period_map.get(req.period.upper(), 365 * 3) # default 3Y
    start_date_str = (asof_ts - pd.Timedelta(days=days)).date().isoformat()

    # 2. Volatility
    vol_data = _run_annualized_volatility(
        tickers=req.tickers,
        start_date=start_date_str,
        end_date=end_date_str,
        auto_adjust=req.auto_adjust,
        frequency=req.frequency,
        return_mode="arith"
    )

    # 3. Drawdowns
    dd_data = _run_drawdown(
        tickers=req.tickers,
        start_date=start_date_str,
        end_date=end_date_str,
        auto_adjust=req.auto_adjust,
        include_series=True
    )

    # 4. Risk (VaR/ES)
    cl_list = [float(x.strip()) for x in req.confidence_levels.split(",") if x.strip()]
    risk_data = _run_var_es(
        tickers=req.tickers,
        start_date=start_date_str,
        end_date=end_date_str,
        auto_adjust=req.auto_adjust,
        return_mode="arith",
        confidence_levels=cl_list
    )

    # 5. Cumulative Returns
    cum_returns_data = _run_cum_returns(
        tickers=req.tickers,
        start_date=start_date_str,
        end_date=end_date_str,
        auto_adjust=req.auto_adjust,
        format="json"
    )

    return YahooAllMetricsResponse(
        perf=YahooPerfResponse(**perf_data),
        vol=YahooAnnVolResponse(**vol_data),
        dd=YahooDrawdownResponse(**dd_data),
        risk=YahooVaREsResponse(**risk_data),
        cum_returns=YahooCumReturnsResponse(**cum_returns_data)
    )


# =========================
# Monte Carlo simulation
# =========================

def _business_dates_forward(start: pd.Timestamp, n_steps: int) -> List[str]:
    """Returns n_steps+1 business-day dates starting from `start` inclusive."""
    idx = pd.bdate_range(start=start, periods=n_steps + 1)
    return [d.date().isoformat() for d in idx]


def _simulate_gbm_paths(
    mu: np.ndarray,
    cov: np.ndarray,
    weights: np.ndarray,
    horizon: int,
    n_sims: int,
    seed: int,
    initial_value: float,
) -> np.ndarray:
    """
    Multivariate GBM. mu and cov are DAILY log-return parameters.
    Returns: portfolio paths array, shape (n_sims, horizon + 1).
    """
    n_assets = len(mu)
    # Jitter on the diagonal for Cholesky numerical stability
    jitter = 1e-10 * np.eye(n_assets)
    try:
        L = np.linalg.cholesky(cov + jitter)
    except np.linalg.LinAlgError:
        # Fallback: eigen-decomposition with clipped negative eigenvalues
        w, V = np.linalg.eigh(cov)
        w = np.clip(w, 1e-12, None)
        L = V @ np.diag(np.sqrt(w))

    rng = np.random.default_rng(seed)
    # Drift correction term (Ito): mu - 0.5 * diag(cov)
    drift = mu - 0.5 * np.diag(cov)

    # Z ~ standard normal: (n_sims, horizon, n_assets)
    Z = rng.standard_normal((n_sims, horizon, n_assets))
    # Correlated shocks via Cholesky
    correlated = Z @ L.T  # (n_sims, horizon, n_assets)
    # Daily log-returns per asset, per path
    log_rets = drift + correlated  # broadcasts drift over (sims, horizon)
    # Cumulative log-returns -> asset prices (normalized to 1 at t=0)
    cum_log_rets = np.cumsum(log_rets, axis=1)
    asset_paths = np.exp(cum_log_rets)  # (n_sims, horizon, n_assets)
    # Portfolio value at each step = weighted sum of asset prices (initial portfolio = 1)
    portfolio_paths = asset_paths @ weights  # (n_sims, horizon)
    # Prepend initial value (t=0)
    initial_col = np.ones((n_sims, 1))
    portfolio_paths = np.concatenate([initial_col, portfolio_paths], axis=1)
    return portfolio_paths * float(initial_value)


def _run_monte_carlo(
    tickers: List[str],
    weights: List[float],
    horizon_days: int,
    n_simulations: int,
    lookback_period: str,
    auto_adjust: bool,
    seed: int,
    n_sample_paths: int,
    initial_value: float,
) -> Dict[str, Any]:
    if len(tickers) != len(weights):
        raise ValueError("tickers and weights must have the same length")

    w_arr = np.array(weights, dtype=float)
    if np.any(w_arr < 0):
        raise ValueError("weights must be non-negative")
    w_sum = w_arr.sum()
    if w_sum <= 0:
        raise ValueError("sum of weights must be > 0")
    w_arr = w_arr / w_sum  # normalize

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    cache_key = (
        "mc",
        tuple(tickers),
        tuple(round(float(x), 6) for x in w_arr.tolist()),
        horizon_days,
        n_simulations,
        lookback_period,
        auto_adjust,
        seed,
        n_sample_paths,
        round(float(initial_value), 6),
        end_ts.date().isoformat(),
    )
    if cache_key in MC_CACHE:
        return MC_CACHE[cache_key]

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    # Keep tickers that actually downloaded; drop weight components for missing tickers
    available = [t for t in tickers if t in close.columns]
    errors: Dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    if not available:
        raise ValueError("No tickers available in downloaded data")

    keep_mask = np.array([t in close.columns for t in tickers])
    w_kept = w_arr[keep_mask]
    w_kept = w_kept / w_kept.sum()  # re-normalize after dropping missing

    prices = close[available].dropna(how="any")
    if len(prices) < 30:
        raise ValueError("Not enough historical price observations (need >= 30)")

    log_rets = np.log(prices / prices.shift(1)).dropna()
    if len(log_rets) < 20:
        raise ValueError("Not enough log-return observations")

    mu = log_rets.mean().to_numpy()           # daily mean log-returns
    cov = log_rets.cov().to_numpy()           # daily covariance matrix

    paths = _simulate_gbm_paths(
        mu=mu,
        cov=cov,
        weights=w_kept,
        horizon=horizon_days,
        n_sims=n_simulations,
        seed=seed,
        initial_value=initial_value,
    )

    pcts = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    p5, p25, p50, p75, p95 = pcts[0], pcts[1], pcts[2], pcts[3], pcts[4]

    # Sample a few representative paths to draw on top of the fan chart
    rng = np.random.default_rng(seed + 1)
    n_samples = min(n_sample_paths, n_simulations)
    sample_idx = rng.choice(n_simulations, size=n_samples, replace=False) if n_samples > 0 else []
    samples = paths[sample_idx].tolist() if n_samples > 0 else []

    dates = _business_dates_forward(end_ts, horizon_days)

    # Portfolio-level annualized drift / vol from estimated params (sanity stats)
    port_daily_mu = float(np.dot(w_kept, mu))
    port_daily_var = float(w_kept @ cov @ w_kept)
    ann_drift = port_daily_mu * 252.0
    ann_vol = float(np.sqrt(max(port_daily_var, 0.0)) * np.sqrt(252.0))

    final_vals = paths[:, -1]
    prob_positive = float(np.mean(final_vals > initial_value))

    out = {
        "dates": dates,
        "percentiles": {
            "p5": p5.tolist(),
            "p25": p25.tolist(),
            "p50": p50.tolist(),
            "p75": p75.tolist(),
            "p95": p95.tolist(),
        },
        "samples": samples,
        "stats": {
            "n_simulations": int(n_simulations),
            "horizon_days": int(horizon_days),
            "lookback_start": str(log_rets.index[0].date().isoformat()),
            "lookback_end": str(log_rets.index[-1].date().isoformat()),
            "initial_value": float(initial_value),
            "expected_final": float(np.mean(final_vals)),
            "p5_final": float(p5[-1]),
            "p25_final": float(p25[-1]),
            "p50_final": float(p50[-1]),
            "p75_final": float(p75[-1]),
            "p95_final": float(p95[-1]),
            "annualized_drift": ann_drift,
            "annualized_volatility": ann_vol,
            "prob_positive": prob_positive,
        },
        "tickers": available,
        "weights": w_kept.tolist(),
        "errors": errors,
    }
    MC_CACHE[cache_key] = out
    return out


@router.post("/yahoo/monte-carlo", response_model=MonteCarloResponse)
def yahoo_monte_carlo_post(req: MonteCarloRequest):
    try:
        return _run_monte_carlo(
            tickers=req.tickers,
            weights=req.weights,
            horizon_days=req.horizon_days,
            n_simulations=req.n_simulations,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            seed=req.seed,
            n_sample_paths=req.n_sample_paths,
            initial_value=req.initial_value,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))