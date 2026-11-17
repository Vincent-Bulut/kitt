"""Risk endpoints."""

from fastapi import APIRouter, HTTPException, Query

from backend.api.analytics.schemas import (
    MonteCarloRequest,
    MonteCarloResponse,
    PortfolioVaREsRequest,
    PortfolioVaREsResponse,
    ReturnMode,
    YahooVaREsRequest,
    YahooVaREsResponse,
)
from backend.api.analytics.services.risk import run_monte_carlo, run_portfolio_var_es, run_var_es

router = APIRouter()


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

    return run_var_es(
        tickers=ticker_list,
        start_date=start_date,
        end_date=end_date,
        auto_adjust=auto_adjust,
        return_mode=return_mode,
        confidence_levels=cl_list,
    )


@router.post("/yahoo/var-es", response_model=YahooVaREsResponse)
def yahoo_var_es_post(req: YahooVaREsRequest):
    return run_var_es(
        tickers=req.tickers,
        start_date=req.start_date,
        end_date=req.end_date,
        auto_adjust=req.auto_adjust,
        return_mode=req.return_mode,
        confidence_levels=req.confidence_levels,
    )


@router.post("/yahoo/monte-carlo", response_model=MonteCarloResponse)
def yahoo_monte_carlo_post(req: MonteCarloRequest):
    try:
        return run_monte_carlo(
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
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/yahoo/portfolio-var-es", response_model=PortfolioVaREsResponse)
def yahoo_portfolio_var_es_post(req: PortfolioVaREsRequest):
    try:
        return run_portfolio_var_es(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            confidence_levels=req.confidence_levels,
            horizon_days=req.horizon_days,
            portfolio_value=req.portfolio_value,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
