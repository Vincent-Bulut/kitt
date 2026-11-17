"""Portfolio diagnostics and construction endpoints."""

import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.api.analytics.schemas import (
    BlackLittermanRequest,
    BlackLittermanResponse,
    CorrelationRequest,
    CorrelationResponse,
    EfficientFrontierRequest,
    EfficientFrontierResponse,
    PCARiskRequest,
    PCARiskResponse,
    PortfolioHealthRequest,
    PortfolioHealthResponse,
    PortfolioRegressionRequest,
    PortfolioRegressionResponse,
    PortfolioSamplerRequest,
    PortfolioSamplerResponse,
)
from backend.api.analytics.services.optimization import (
    BL_CACHE,
    run_black_litterman,
    run_efficient_frontier,
    run_portfolio_sampler,
)
from backend.api.analytics.services.portfolio import (
    run_correlation,
    run_pca_risk,
    run_portfolio_health,
    run_portfolio_regression,
)

router = APIRouter()


@router.post("/yahoo/correlation", response_model=CorrelationResponse)
def yahoo_correlation_post(req: CorrelationRequest):
    try:
        return run_correlation(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            return_mode=req.return_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/yahoo/portfolio-health", response_model=PortfolioHealthResponse)
def yahoo_portfolio_health_post(req: PortfolioHealthRequest):
    try:
        return run_portfolio_health(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            risk_free_rate=req.risk_free_rate,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/yahoo/efficient-frontier", response_model=EfficientFrontierResponse)
def yahoo_efficient_frontier_post(req: EfficientFrontierRequest):
    try:
        return run_efficient_frontier(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            risk_free_rate=req.risk_free_rate,
            n_points=req.n_points,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/yahoo/black-litterman", response_model=BlackLittermanResponse)
def yahoo_black_litterman_post(req: BlackLittermanRequest):
    cache_key = (
        "bl",
        tuple(req.tickers),
        None if req.prior_weights is None else tuple(round(float(x), 6) for x in req.prior_weights),
        tuple((v.view_type, v.asset, v.asset_other, round(v.value, 6), round(v.confidence, 4)) for v in req.views),
        req.lookback_period,
        req.auto_adjust,
        round(float(req.risk_free_rate), 6),
        round(float(req.risk_aversion), 4),
        round(float(req.tau), 6),
        round(float(req.max_weight), 4),
        round(float(req.min_weight), 4),
        pd.Timestamp.now().normalize().date().isoformat(),
    )
    if cache_key in BL_CACHE:
        return BL_CACHE[cache_key]
    try:
        out = run_black_litterman(
            tickers=req.tickers,
            prior_weights=req.prior_weights,
            views=req.views,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            risk_free_rate=req.risk_free_rate,
            risk_aversion=req.risk_aversion,
            tau=req.tau,
            max_weight=req.max_weight,
            min_weight=req.min_weight,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    BL_CACHE[cache_key] = out
    return out


@router.post("/yahoo/portfolio-sampler", response_model=PortfolioSamplerResponse)
def yahoo_portfolio_sampler_post(req: PortfolioSamplerRequest):
    try:
        return run_portfolio_sampler(
            tickers=req.tickers,
            portfolio_size=req.portfolio_size,
            n_simulations=req.n_simulations,
            top_k=req.top_k,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            risk_free_rate=req.risk_free_rate,
            diversification_weight=req.diversification_weight,
            max_weight=req.max_weight,
            min_weight=req.min_weight,
            optimization=req.optimization,
            seed=req.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/yahoo/pca-risk", response_model=PCARiskResponse)
def yahoo_pca_risk_post(req: PCARiskRequest):
    try:
        return run_pca_risk(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            return_mode=req.return_mode,
            matrix_type=req.matrix_type,
            n_components=req.n_components,
            top_loadings=req.top_loadings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/yahoo/portfolio-regression", response_model=PortfolioRegressionResponse)
def yahoo_portfolio_regression_post(req: PortfolioRegressionRequest):
    try:
        return run_portfolio_regression(
            tickers=req.tickers,
            weights=req.weights,
            benchmark=req.benchmark,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            frequency=req.frequency,
            base_currency=req.base_currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
