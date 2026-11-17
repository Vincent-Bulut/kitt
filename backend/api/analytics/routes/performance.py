"""Performance endpoints."""

from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Query

from backend.api import utils
from backend.api.analytics.routes.params import check_date_range, parse_confidence_levels, parse_tickers
from backend.api.analytics.schemas import (
    IsoDate,
    ReturnMode,
    VolFrequency,
    YahooAllMetricsRequest,
    YahooAllMetricsResponse,
    YahooAnnVolRequest,
    YahooAnnVolResponse,
    YahooCumReturnsRequest,
    YahooCumReturnsResponse,
    YahooDrawdownRequest,
    YahooDrawdownResponse,
    YahooPerfRequest,
    YahooPerfResponse,
    YahooReturnRequest,
    YahooReturnResponse,
    YahooVaREsResponse,
)
from backend.api.analytics.services.performance import (
    run_annualized_volatility,
    run_arithmetic_return,
    run_cum_returns,
    run_drawdown,
    run_perf,
)
from backend.api.analytics.services.risk import run_var_es

router = APIRouter()


@router.get("/yahoo/perf", response_model=YahooPerfResponse)
def yahoo_perf_get(
    tickers: Annotated[str, Query(description="Comma-separated: AAPL,SPY,AIR.PA")],
    asof: Annotated[IsoDate | None, Query(description="YYYY-MM-DD")] = None,
    auto_adjust: bool = True,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    ticker_list = parse_tickers(tickers, max_tickers=500)

    return run_perf(ticker_list, asof, auto_adjust, format)


@router.post("/yahoo/perf-table", response_model=YahooPerfResponse)
def yahoo_perf_post(
    req: YahooPerfRequest,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    return run_perf(req.tickers, req.asof, req.auto_adjust, format)


@router.get("/yahoo/arithmetic-return", response_model=YahooReturnResponse)
def yahoo_arithmetic_return_get(
    tickers: Annotated[str, Query(description="Comma-separated: AAPL,SPY,AIR.PA")],
    start_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    end_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    auto_adjust: bool = True,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    ticker_list = parse_tickers(tickers, max_tickers=500)
    check_date_range(start_date, end_date)

    return run_arithmetic_return(ticker_list, start_date, end_date, auto_adjust, format)


@router.post("/yahoo/arithmetic-return", response_model=YahooReturnResponse)
def yahoo_arithmetic_return_post(
    req: YahooReturnRequest,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    return run_arithmetic_return(req.tickers, req.start_date, req.end_date, req.auto_adjust, format)


@router.get("/yahoo/cumulative-returns", response_model=YahooCumReturnsResponse)
def yahoo_cumulative_returns_get(
    tickers: Annotated[str, Query(description="Comma-separated: AAPL,SPY,AIR.PA")],
    start_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    end_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    auto_adjust: bool = True,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    ticker_list = parse_tickers(tickers, max_tickers=200)
    check_date_range(start_date, end_date)

    return run_cum_returns(ticker_list, start_date, end_date, auto_adjust, format)


@router.post("/yahoo/cumulative-returns", response_model=YahooCumReturnsResponse)
def yahoo_cumulative_returns_post(
    req: YahooCumReturnsRequest,
    format: str = Query("json", pattern="^(json|csv)$"),
):
    return run_cum_returns(req.tickers, req.start_date, req.end_date, req.auto_adjust, format)


@router.get("/yahoo/drawdowns", response_model=YahooDrawdownResponse)
def yahoo_drawdowns_get(
    tickers: Annotated[str, Query(description="Comma-separated: AAPL,SPY,AIR.PA")],
    start_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    end_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    auto_adjust: bool = True,
    include_series: bool = False,
):
    ticker_list = parse_tickers(tickers, max_tickers=200)
    check_date_range(start_date, end_date)

    return run_drawdown(ticker_list, start_date, end_date, auto_adjust, include_series)


@router.post("/yahoo/drawdowns", response_model=YahooDrawdownResponse)
def yahoo_drawdowns_post(req: YahooDrawdownRequest):
    return run_drawdown(req.tickers, req.start_date, req.end_date, req.auto_adjust, req.include_series)


@router.get("/yahoo/annualized-volatility", response_model=YahooAnnVolResponse)
def yahoo_annualized_volatility_get(
    tickers: Annotated[str, Query(description="Comma-separated: AAPL,SPY,AIR.PA")],
    start_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    end_date: Annotated[IsoDate, Query(description="YYYY-MM-DD")],
    auto_adjust: bool = True,
    frequency: VolFrequency = Query("daily", description="daily|weekly|monthly"),
    return_mode: ReturnMode = Query("log", description="log|arith"),
):
    ticker_list = parse_tickers(tickers, max_tickers=200)
    check_date_range(start_date, end_date)

    return run_annualized_volatility(
        tickers=ticker_list,
        start_date=start_date,
        end_date=end_date,
        auto_adjust=auto_adjust,
        frequency=frequency,
        return_mode=return_mode,
    )


@router.post("/yahoo/annualized-volatility", response_model=YahooAnnVolResponse)
def yahoo_annualized_volatility_post(req: YahooAnnVolRequest):
    return run_annualized_volatility(
        tickers=req.tickers,
        start_date=req.start_date,
        end_date=req.end_date,
        auto_adjust=req.auto_adjust,
        frequency=req.frequency,
        return_mode=req.return_mode,
    )


@router.post("/yahoo/all-metrics", response_model=YahooAllMetricsResponse)
def yahoo_all_metrics_post(req: YahooAllMetricsRequest):
    # 1. Performance
    perf_data = run_perf(
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
    vol_data = run_annualized_volatility(
        tickers=req.tickers,
        start_date=start_date_str,
        end_date=end_date_str,
        auto_adjust=req.auto_adjust,
        frequency=req.frequency,
        return_mode="arith"
    )

    # 3. Drawdowns
    dd_data = run_drawdown(
        tickers=req.tickers,
        start_date=start_date_str,
        end_date=end_date_str,
        auto_adjust=req.auto_adjust,
        include_series=True
    )

    # 4. Risk (VaR/ES)
    cl_list = parse_confidence_levels(req.confidence_levels)
    risk_data = run_var_es(
        tickers=req.tickers,
        start_date=start_date_str,
        end_date=end_date_str,
        auto_adjust=req.auto_adjust,
        return_mode="arith",
        confidence_levels=cl_list
    )

    # 5. Cumulative Returns
    cum_returns_data = run_cum_returns(
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
