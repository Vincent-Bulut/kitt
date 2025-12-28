import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

import yfinance as yf
from cachetools import TTLCache

import utils

router = APIRouter(prefix='/analytics', tags=['ANALYTICS'])


PERIODS = ["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]
Period = Literal["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]

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

