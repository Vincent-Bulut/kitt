import io
import pandas as pd
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any, Tuple
from scipy.stats import norm
from scipy.optimize import minimize

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

CORR_CACHE = TTLCache(maxsize=500, ttl=600)

HEALTH_CACHE = TTLCache(maxsize=500, ttl=600)

EF_CACHE = TTLCache(maxsize=200, ttl=600)

SAMPLER_CACHE = TTLCache(maxsize=100, ttl=600)

BL_CACHE = TTLCache(maxsize=200, ttl=600)

PCA_CACHE = TTLCache(maxsize=200, ttl=600)

PORTVAR_CACHE = TTLCache(maxsize=500, ttl=600)

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


class CorrelationPair(BaseModel):
    ticker_a: str
    ticker_b: str
    correlation: float


class CorrelationStats(BaseModel):
    avg_correlation: float                # mean of upper-triangle (off-diagonal) values
    weighted_avg_correlation: Optional[float] = None  # weighted by w_i * w_j on off-diagonal
    min_pair: Optional[CorrelationPair] = None
    max_pair: Optional[CorrelationPair] = None
    pct_pairs_above_0_7: float            # share of pairs with corr > 0.7
    pct_pairs_below_0_3: float            # share of pairs with corr < 0.3
    diversification_score: float          # 1 - avg_correlation (clamped to [0,1])
    n_pairs: int


class CorrelationResponse(BaseModel):
    tickers: List[str]
    matrix: List[List[float]]             # square matrix, indexed by tickers
    observations: int
    start_date_used: str
    end_date_used: str
    stats: CorrelationStats
    errors: Dict[str, str] = Field(default_factory=dict)


class PortfolioHealthStats(BaseModel):
    annualized_return: float          # arithmetic, decimal (0.10 = 10%)
    annualized_volatility: float      # decimal
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float               # decimal, negative
    best_day: float                   # decimal
    worst_day: float                  # decimal
    pct_positive_days: float          # decimal
    cumulative_return: float          # decimal over the lookback


class PortfolioHealthResponse(BaseModel):
    tickers: List[str]
    weights: List[float]
    observations: int
    start_date_used: str
    end_date_used: str
    risk_free_rate: float
    stats: PortfolioHealthStats
    errors: Dict[str, str] = Field(default_factory=dict)


class FrontierPoint(BaseModel):
    expected_return: float
    volatility: float
    sharpe: float


class PortfolioOnFrontier(BaseModel):
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe: float


class AssetPoint(BaseModel):
    ticker: str
    expected_return: float
    volatility: float


class EfficientFrontierResponse(BaseModel):
    tickers: List[str]
    risk_free_rate: float
    observations: int
    start_date_used: str
    end_date_used: str
    frontier: List[FrontierPoint]
    assets: List[AssetPoint]
    min_variance: PortfolioOnFrontier
    max_sharpe: PortfolioOnFrontier
    current_portfolio: Optional[PortfolioOnFrontier] = None
    errors: Dict[str, str] = Field(default_factory=dict)


SamplerOptimization = Literal["max_sharpe", "equal_weight"]


class SampledPortfolio(BaseModel):
    tickers: List[str]
    weights: List[float]
    expected_return: float
    volatility: float
    sharpe: float
    avg_correlation: float
    composite_score: float


class SamplerCloudPoint(BaseModel):
    volatility: float
    expected_return: float
    sharpe: float
    avg_correlation: float
    composite_score: float
    tickers: List[str]
    weights: List[float]


class PortfolioSamplerResponse(BaseModel):
    universe: List[str]
    portfolio_size: int
    n_simulations_requested: int
    n_simulations_evaluated: int
    n_simulations_failed: int
    observations: int
    start_date_used: str
    end_date_used: str
    risk_free_rate: float
    diversification_weight: float
    optimization: SamplerOptimization
    top_by_composite: List[SampledPortfolio]
    top_by_sharpe: List[SampledPortfolio]
    cloud: List[SamplerCloudPoint]
    errors: Dict[str, str] = Field(default_factory=dict)


class PortfolioSamplerRequest(BaseModel):
    tickers: List[str] = Field(min_length=2, max_length=300)
    portfolio_size: int = Field(default=5, ge=2, le=20)
    n_simulations: int = Field(default=200, ge=10, le=5000)
    top_k: int = Field(default=5, ge=1, le=50)
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    risk_free_rate: float = Field(default=0.02, ge=0.0, le=0.5)
    diversification_weight: float = Field(default=1.0, ge=0.0, le=5.0)
    max_weight: float = Field(default=1.0, ge=0.05, le=1.0)
    min_weight: float = Field(default=0.0, ge=0.0, le=0.5)
    optimization: SamplerOptimization = "max_sharpe"
    seed: int = 42


class EfficientFrontierRequest(BaseModel):
    tickers: List[str] = Field(min_length=2, max_length=50)
    weights: Optional[List[float]] = None
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    risk_free_rate: float = Field(default=0.02, ge=0.0, le=0.5)
    n_points: int = Field(default=40, ge=10, le=120)


# --- Black-Litterman ---

BLViewType = Literal["absolute", "relative"]


class BLView(BaseModel):
    # "absolute": asset expected to return `value` (annualized total return).
    # "relative": `asset` expected to outperform `asset_other` by `value` (annualized).
    view_type: BLViewType = "absolute"
    asset: str
    asset_other: Optional[str] = None
    value: float                                             # annualized return / spread
    confidence: float = Field(default=0.5, gt=0.0, le=1.0)   # 0..1, higher = view pulls harder


class BLAssetPoint(BaseModel):
    ticker: str
    prior_return: float          # implied equilibrium (annualized)
    posterior_return: float      # Black-Litterman blended return (annualized)
    volatility: float
    prior_weight: float          # market / equilibrium weight
    optimal_weight: float        # max-Sharpe weight on posterior returns


class BlackLittermanResponse(BaseModel):
    tickers: List[str]
    risk_free_rate: float
    risk_aversion: float
    tau: float
    observations: int
    start_date_used: str
    end_date_used: str
    assets: List[BLAssetPoint]
    prior_weights: Dict[str, float]
    implied_returns: Dict[str, float]
    posterior_returns: Dict[str, float]
    optimal: PortfolioOnFrontier          # max-Sharpe on posterior returns
    min_variance: PortfolioOnFrontier
    n_views_applied: int
    warnings: List[str] = Field(default_factory=list)
    errors: Dict[str, str] = Field(default_factory=dict)


class BlackLittermanRequest(BaseModel):
    tickers: List[str] = Field(min_length=2, max_length=50)
    prior_weights: Optional[List[float]] = None             # market / equilibrium weights; default equal
    views: List[BLView] = Field(default_factory=list)
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    risk_free_rate: float = Field(default=0.02, ge=0.0, le=0.5)
    risk_aversion: float = Field(default=2.5, ge=0.1, le=20.0)
    tau: float = Field(default=0.05, gt=0.0, le=1.0)
    max_weight: float = Field(default=1.0, ge=0.05, le=1.0)
    min_weight: float = Field(default=0.0, ge=0.0, le=0.5)


# --- PCA / eigen risk decomposition ---

PCAMatrixType = Literal["covariance", "correlation"]


class PCAComponent(BaseModel):
    index: int                                      # 1-based principal component number
    eigenvalue: float                               # variance carried by the component (annualized)
    factor_volatility: float                        # sqrt(eigenvalue) = annualized vol of the factor
    explained_variance_ratio: float                 # eigenvalue / trace of the diagonalized matrix
    cumulative_explained: float
    portfolio_exposure: float                       # y_i = v_i' w~  (signed coordinate in eigenbasis)
    variance_contribution: float                    # lambda_i * y_i^2 (annualized variance)
    variance_contribution_pct: float                # share of portfolio variance
    cumulative_variance_contribution_pct: float
    risk_contribution: float                        # lambda_i * y_i^2 / sigma_p (vol units, sums to sigma_p)
    loadings: Dict[str, float]                      # ticker -> eigenvector coefficient
    top_positive: List[str]
    top_negative: List[str]
    interpretation: str


class PCAAssetRisk(BaseModel):
    ticker: str
    weight: float
    volatility: float                               # annualized
    marginal_contribution_to_risk: float            # (Sigma w)_i / sigma_p
    contribution_to_risk: float                     # w_i * MCTR_i (sums to sigma_p)
    contribution_to_risk_pct: float                 # share of portfolio risk
    pc1_loading: float
    pc1_communality: float                          # share of the asset's own variance explained by PC1
    top_component: int                              # 1-based PC this asset loads most on


class PCAStats(BaseModel):
    portfolio_volatility: float                     # annualized
    portfolio_variance: float
    total_matrix_variance: float                    # trace of the diagonalized matrix
    pc1_explained_ratio: float                      # PC1 share of the matrix variance
    pc1_variance_contribution_pct: float            # PC1 share of *your* portfolio variance
    n_components_for_80_matrix: int
    n_components_for_90_matrix: int
    n_components_for_90_portfolio_risk: int
    effective_number_of_bets: float                 # exp(entropy of portfolio variance contributions)
    max_contribution_pct: float
    diversification_ratio: float                    # sum(w_i * sigma_i) / sigma_p
    weighted_avg_volatility: float
    condition_number: float                         # lambda_max / lambda_min (redundancy flag)


class PCARiskResponse(BaseModel):
    tickers: List[str]
    weights: List[float]
    matrix_type: PCAMatrixType
    return_mode: ReturnMode
    observations: int
    start_date_used: str
    end_date_used: str
    covariance: List[List[float]]                   # annualized variance-covariance matrix
    matrix: List[List[float]]                       # the matrix actually diagonalized
    components: List[PCAComponent]
    assets: List[PCAAssetRisk]
    stats: PCAStats
    warnings: List[str] = Field(default_factory=list)
    errors: Dict[str, str] = Field(default_factory=dict)


class PCARiskRequest(BaseModel):
    tickers: List[str] = Field(min_length=2, max_length=100)
    weights: Optional[List[float]] = None           # portfolio weights; default equal
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    return_mode: ReturnMode = "log"
    matrix_type: PCAMatrixType = "covariance"
    n_components: int = Field(default=10, ge=1, le=100)   # how many components to detail
    top_loadings: int = Field(default=3, ge=1, le=10)     # tickers named per side in each PC


class PortfolioVaRContribution(BaseModel):
    ticker: str
    weight: float
    volatility: float                               # annualized standalone volatility
    standalone_var: float                           # the asset's own historical VaR over the horizon
    beta_to_portfolio: float                        # cov(r_i, r_p) / var(r_p)
    marginal_var: float                             # dVaR_gaussian / dw_i
    component_var: float                            # w_i * marginal_var (sums to var_gaussian)
    component_var_pct: float                        # share of the portfolio Gaussian VaR
    component_es: float                             # -w_i * mean(r_i | tail days) (sums to es_historical)
    component_es_pct: float                         # share of the portfolio historical ES


class PortfolioVaREsPoint(BaseModel):
    confidence_level: float

    # Portfolio-level losses, expressed as a positive fraction of portfolio value
    var_historical: float
    es_historical: float
    var_gaussian: float
    es_gaussian: float
    var_cornish_fisher: float
    es_cf_empirical_tail: float

    # Same figures in portfolio currency (0.0 when no portfolio_value was supplied)
    var_historical_value: float
    es_historical_value: float
    var_gaussian_value: float
    es_gaussian_value: float
    var_cornish_fisher_value: float
    es_cf_empirical_tail_value: float

    # Diversification: what the VaR would be if the holdings never offset each other
    undiversified_var: float                        # sum(w_i * standalone historical VaR_i)
    diversification_benefit: float                  # undiversified_var - var_historical
    diversification_benefit_pct: float              # benefit / undiversified_var

    # Normality check: how often the realized loss actually broke the Gaussian VaR
    gaussian_breaches: int
    gaussian_breach_rate: float
    expected_breach_rate: float                     # 1 - confidence_level

    contributions: List[PortfolioVaRContribution]


class PortfolioVaREsStats(BaseModel):
    portfolio_volatility: float                     # volatility of the horizon return
    portfolio_volatility_annualized: float
    weighted_avg_volatility: float                  # annualized sum(w_i * sigma_i)
    diversification_ratio: float                    # weighted_avg_volatility / portfolio_volatility_annualized
    mean_return: float                              # mean horizon return
    skewness: float
    excess_kurtosis: float
    worst_return: float
    worst_return_date: str
    best_return: float


class PortfolioVaREsResponse(BaseModel):
    tickers: List[str]
    weights: List[float]
    lookback_period: str
    return_mode: ReturnMode                         # always "arith" — VaR is a P&L of a linear position
    horizon_days: int
    observations: int
    start_date_used: str
    end_date_used: str
    price_type: str                                 # "Adjusted Close" or "Close"
    portfolio_value: Optional[float] = None
    stats: PortfolioVaREsStats
    points: List[PortfolioVaREsPoint]
    warnings: List[str] = Field(default_factory=list)
    errors: Dict[str, str] = Field(default_factory=dict)


class PortfolioVaREsRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=100)
    weights: Optional[List[float]] = None           # portfolio weights; default equal
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    confidence_levels: List[float] = Field(default_factory=lambda: [0.95, 0.99])
    horizon_days: int = Field(default=1, ge=1, le=60)
    portfolio_value: Optional[float] = Field(default=None, gt=0)


class PortfolioHealthRequest(BaseModel):
    tickers: List[str] = Field(min_length=1, max_length=100)
    weights: List[float] = Field(min_length=1, max_length=100)
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    risk_free_rate: float = Field(default=0.02, ge=0.0, le=0.5)


class CorrelationRequest(BaseModel):
    tickers: List[str] = Field(min_length=2, max_length=100)
    weights: Optional[List[float]] = None  # if provided, used for weighted avg correlation
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    return_mode: ReturnMode = "log"


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


# =========================
# Correlation matrix
# =========================

def _run_correlation(
    tickers: List[str],
    weights: Optional[List[float]],
    lookback_period: str,
    auto_adjust: bool,
    return_mode: ReturnMode,
) -> Dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required to compute a correlation matrix")

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    norm_weights: Optional[np.ndarray] = None
    if weights is not None:
        if len(weights) != len(tickers):
            raise ValueError("weights length must match tickers length")
        w = np.array(weights, dtype=float)
        if np.any(w < 0):
            raise ValueError("weights must be non-negative")
        s = w.sum()
        if s > 0:
            norm_weights = w / s

    cache_key = (
        "corr",
        tuple(tickers),
        None if norm_weights is None else tuple(round(float(x), 6) for x in norm_weights.tolist()),
        lookback_period,
        auto_adjust,
        return_mode,
        end_ts.date().isoformat(),
    )
    if cache_key in CORR_CACHE:
        return CORR_CACHE[cache_key]

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: Dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    if len(available) < 2:
        raise ValueError("Need at least 2 tickers with price data to compute correlations")

    # Re-align weights to available tickers (renormalize)
    if norm_weights is not None:
        keep_mask = np.array([t in close.columns for t in tickers])
        w_kept = norm_weights[keep_mask]
        s2 = w_kept.sum()
        norm_weights = (w_kept / s2) if s2 > 0 else None

    prices = close[available].dropna(how="any")
    if len(prices) < 20:
        raise ValueError("Not enough overlapping price observations (need >= 20)")

    if return_mode == "log":
        rets = np.log(prices / prices.shift(1)).dropna()
    else:
        rets = prices.pct_change().dropna()

    if len(rets) < 10:
        raise ValueError("Not enough return observations to compute correlations")

    corr = rets.corr().reindex(index=available, columns=available)
    corr_vals = corr.to_numpy()

    n = len(available)
    iu = np.triu_indices(n, k=1)  # upper triangle, off-diagonal
    off_diag = corr_vals[iu]

    avg_corr = float(np.nanmean(off_diag)) if off_diag.size else 0.0

    weighted_avg: Optional[float] = None
    if norm_weights is not None and norm_weights.size == n:
        # Weighted off-diagonal mean: sum_{i<j} 2*w_i*w_j*rho_ij / sum_{i<j} 2*w_i*w_j
        ww = np.outer(norm_weights, norm_weights)
        num = float(np.nansum(ww[iu] * off_diag))
        den = float(np.nansum(ww[iu]))
        weighted_avg = float(num / den) if den > 0 else None

    min_pair_obj: Optional[Dict[str, Any]] = None
    max_pair_obj: Optional[Dict[str, Any]] = None
    if off_diag.size:
        flat_idx_min = int(np.nanargmin(off_diag))
        flat_idx_max = int(np.nanargmax(off_diag))
        i_min, j_min = iu[0][flat_idx_min], iu[1][flat_idx_min]
        i_max, j_max = iu[0][flat_idx_max], iu[1][flat_idx_max]
        min_pair_obj = {
            "ticker_a": available[i_min],
            "ticker_b": available[j_min],
            "correlation": float(off_diag[flat_idx_min]),
        }
        max_pair_obj = {
            "ticker_a": available[i_max],
            "ticker_b": available[j_max],
            "correlation": float(off_diag[flat_idx_max]),
        }

    n_pairs = int(off_diag.size)
    pct_high = float(np.nansum(off_diag > 0.7) / n_pairs) if n_pairs else 0.0
    pct_low = float(np.nansum(off_diag < 0.3) / n_pairs) if n_pairs else 0.0
    diversification_score = float(max(0.0, min(1.0, 1.0 - avg_corr)))

    out = {
        "tickers": available,
        "matrix": [[float(v) for v in row] for row in corr_vals],
        "observations": int(len(rets)),
        "start_date_used": rets.index[0].date().isoformat(),
        "end_date_used": rets.index[-1].date().isoformat(),
        "stats": {
            "avg_correlation": avg_corr,
            "weighted_avg_correlation": weighted_avg,
            "min_pair": min_pair_obj,
            "max_pair": max_pair_obj,
            "pct_pairs_above_0_7": pct_high,
            "pct_pairs_below_0_3": pct_low,
            "diversification_score": diversification_score,
            "n_pairs": n_pairs,
        },
        "errors": errors,
    }
    CORR_CACHE[cache_key] = out
    return out


@router.post("/yahoo/correlation", response_model=CorrelationResponse)
def yahoo_correlation_post(req: CorrelationRequest):
    try:
        return _run_correlation(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            return_mode=req.return_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================
# Portfolio health (Sharpe / Sortino / Calmar / …)
# =========================

def _run_portfolio_health(
    tickers: List[str],
    weights: List[float],
    lookback_period: str,
    auto_adjust: bool,
    risk_free_rate: float,
) -> Dict[str, Any]:
    if len(tickers) != len(weights):
        raise ValueError("tickers and weights must have the same length")

    w_arr = np.array(weights, dtype=float)
    if np.any(w_arr < 0):
        raise ValueError("weights must be non-negative")
    w_sum = w_arr.sum()
    if w_sum <= 0:
        raise ValueError("sum of weights must be > 0")
    w_arr = w_arr / w_sum

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    cache_key = (
        "health",
        tuple(tickers),
        tuple(round(float(x), 6) for x in w_arr.tolist()),
        lookback_period,
        auto_adjust,
        round(float(risk_free_rate), 6),
        end_ts.date().isoformat(),
    )
    if cache_key in HEALTH_CACHE:
        return HEALTH_CACHE[cache_key]

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: Dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    if not available:
        raise ValueError("No tickers available in downloaded data")

    keep_mask = np.array([t in close.columns for t in tickers])
    w_kept = w_arr[keep_mask]
    s_kept = w_kept.sum()
    if s_kept <= 0:
        raise ValueError("All weights map to missing tickers")
    w_kept = w_kept / s_kept

    prices = close[available].dropna(how="any")
    if len(prices) < 20:
        raise ValueError("Not enough overlapping price observations (need >= 20)")

    # Arithmetic daily returns per asset
    asset_rets = prices.pct_change().dropna()
    if len(asset_rets) < 10:
        raise ValueError("Not enough return observations to compute ratios")

    # Portfolio daily returns = weighted sum (fixed-weight rebalanced daily)
    port_rets = asset_rets.to_numpy() @ w_kept  # 1D array

    # Annualization
    ann_factor = 252.0
    daily_mean = float(np.mean(port_rets))
    daily_std = float(np.std(port_rets, ddof=1)) if len(port_rets) > 1 else 0.0
    ann_return = daily_mean * ann_factor
    ann_vol = daily_std * float(np.sqrt(ann_factor))

    # Sharpe
    if ann_vol > 0:
        sharpe = (ann_return - float(risk_free_rate)) / ann_vol
    else:
        sharpe = 0.0

    # Sortino: downside deviation w.r.t. Rf daily
    rf_daily = float(risk_free_rate) / ann_factor
    downside = port_rets[port_rets < rf_daily] - rf_daily
    if downside.size > 1:
        downside_dev = float(np.sqrt(np.mean(np.square(downside))) * np.sqrt(ann_factor))
    else:
        downside_dev = 0.0
    sortino = ((ann_return - float(risk_free_rate)) / downside_dev) if downside_dev > 0 else 0.0

    # Cumulative return + max drawdown on portfolio NAV
    nav = np.cumprod(1.0 + port_rets)
    cum_return = float(nav[-1] - 1.0)
    running_max = np.maximum.accumulate(nav)
    drawdowns = nav / running_max - 1.0
    max_dd = float(np.min(drawdowns)) if drawdowns.size else 0.0

    # Calmar = annualized return / |max DD|
    calmar = (ann_return / abs(max_dd)) if max_dd < 0 else 0.0

    best_day = float(np.max(port_rets)) if port_rets.size else 0.0
    worst_day = float(np.min(port_rets)) if port_rets.size else 0.0
    pct_positive = float(np.mean(port_rets > 0)) if port_rets.size else 0.0

    out = {
        "tickers": available,
        "weights": w_kept.tolist(),
        "observations": int(len(port_rets)),
        "start_date_used": asset_rets.index[0].date().isoformat(),
        "end_date_used": asset_rets.index[-1].date().isoformat(),
        "risk_free_rate": float(risk_free_rate),
        "stats": {
            "annualized_return": ann_return,
            "annualized_volatility": ann_vol,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": max_dd,
            "best_day": best_day,
            "worst_day": worst_day,
            "pct_positive_days": pct_positive,
            "cumulative_return": cum_return,
        },
        "errors": errors,
    }
    HEALTH_CACHE[cache_key] = out
    return out


@router.post("/yahoo/portfolio-health", response_model=PortfolioHealthResponse)
def yahoo_portfolio_health_post(req: PortfolioHealthRequest):
    try:
        return _run_portfolio_health(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            risk_free_rate=req.risk_free_rate,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================
# Markowitz efficient frontier
# =========================

def _portfolio_perf(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> Tuple[float, float]:
    """Return (expected_return, volatility), both annualized."""
    ret = float(np.dot(weights, mu))
    var = float(weights @ cov @ weights)
    vol = float(np.sqrt(max(var, 0.0)))
    return ret, vol


def _min_variance_for_target(
    target_return: float,
    mu: np.ndarray,
    cov: np.ndarray,
) -> Optional[np.ndarray]:
    n = len(mu)
    w0 = np.full(n, 1.0 / n)
    bounds = [(0.0, 1.0)] * n
    constraints = [
        {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)},
        {"type": "eq", "fun": lambda w, t=target_return: float(np.dot(w, mu) - t)},
    ]
    res = minimize(
        lambda w: float(w @ cov @ w),
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 200, "ftol": 1e-10, "disp": False},
    )
    return res.x if res.success else None


def _min_variance_portfolio(mu: np.ndarray, cov: np.ndarray) -> np.ndarray:
    n = len(mu)
    w0 = np.full(n, 1.0 / n)
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]
    res = minimize(
        lambda w: float(w @ cov @ w),
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 200, "ftol": 1e-10, "disp": False},
    )
    if not res.success:
        raise ValueError(f"Min variance optimization failed: {res.message}")
    return res.x


def _max_sharpe_portfolio(mu: np.ndarray, cov: np.ndarray, rf: float) -> np.ndarray:
    n = len(mu)
    w0 = np.full(n, 1.0 / n)
    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]

    def neg_sharpe(w):
        ret = float(np.dot(w, mu))
        var = float(w @ cov @ w)
        vol = float(np.sqrt(max(var, 1e-18)))
        return -(ret - rf) / vol if vol > 0 else 0.0

    res = minimize(
        neg_sharpe,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 300, "ftol": 1e-10, "disp": False},
    )
    if not res.success:
        raise ValueError(f"Max Sharpe optimization failed: {res.message}")
    return res.x


def _build_portfolio_descriptor(
    w: np.ndarray,
    tickers: List[str],
    mu: np.ndarray,
    cov: np.ndarray,
    rf: float,
) -> Dict[str, Any]:
    ret, vol = _portfolio_perf(w, mu, cov)
    sharpe = ((ret - rf) / vol) if vol > 0 else 0.0
    return {
        "weights": {tickers[i]: float(w[i]) for i in range(len(tickers))},
        "expected_return": ret,
        "volatility": vol,
        "sharpe": sharpe,
    }


def _run_efficient_frontier(
    tickers: List[str],
    weights: Optional[List[float]],
    lookback_period: str,
    auto_adjust: bool,
    risk_free_rate: float,
    n_points: int,
) -> Dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required to compute an efficient frontier")

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    current_w_arr: Optional[np.ndarray] = None
    if weights is not None:
        if len(weights) != len(tickers):
            raise ValueError("weights length must match tickers length")
        w = np.array(weights, dtype=float)
        if np.any(w < 0):
            raise ValueError("weights must be non-negative")
        s = w.sum()
        if s > 0:
            current_w_arr = w / s

    cache_key = (
        "ef",
        tuple(tickers),
        None if current_w_arr is None else tuple(round(float(x), 6) for x in current_w_arr.tolist()),
        lookback_period,
        auto_adjust,
        round(float(risk_free_rate), 6),
        int(n_points),
        end_ts.date().isoformat(),
    )
    if cache_key in EF_CACHE:
        return EF_CACHE[cache_key]

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: Dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    if len(available) < 2:
        raise ValueError("Need at least 2 tickers with price data for the frontier")

    # Re-align current weights to available tickers (renormalize) if provided
    current_w_aligned: Optional[np.ndarray] = None
    if current_w_arr is not None:
        keep_mask = np.array([t in close.columns for t in tickers])
        w_kept = current_w_arr[keep_mask]
        sk = w_kept.sum()
        current_w_aligned = (w_kept / sk) if sk > 0 else None

    prices = close[available].dropna(how="any")
    if len(prices) < 30:
        raise ValueError("Not enough overlapping price observations (need >= 30)")

    log_rets = np.log(prices / prices.shift(1)).dropna()
    if len(log_rets) < 20:
        raise ValueError("Not enough return observations to compute frontier")

    ann_factor = 252.0
    mu = log_rets.mean().to_numpy() * ann_factor                # annualized
    cov = log_rets.cov().to_numpy() * ann_factor                # annualized

    rf = float(risk_free_rate)

    # Special portfolios
    w_minvar = _min_variance_portfolio(mu, cov)
    w_tangent = _max_sharpe_portfolio(mu, cov, rf)

    minvar_desc = _build_portfolio_descriptor(w_minvar, available, mu, cov, rf)
    tangent_desc = _build_portfolio_descriptor(w_tangent, available, mu, cov, rf)

    # Frontier: span from min-var return up to max individual asset return
    r_min = minvar_desc["expected_return"]
    r_max = float(np.max(mu))
    if r_max <= r_min:
        # Edge case: nothing to span — just emit the single point
        targets = np.array([r_min])
    else:
        targets = np.linspace(r_min, r_max, int(n_points))

    frontier_points: List[Dict[str, float]] = []
    for t in targets:
        w_opt = _min_variance_for_target(float(t), mu, cov)
        if w_opt is None:
            continue
        ret, vol = _portfolio_perf(w_opt, mu, cov)
        sharpe = ((ret - rf) / vol) if vol > 0 else 0.0
        frontier_points.append({
            "expected_return": ret,
            "volatility": vol,
            "sharpe": sharpe,
        })

    # Individual assets
    asset_points: List[Dict[str, Any]] = []
    for i, t in enumerate(available):
        sigma_i = float(np.sqrt(max(cov[i, i], 0.0)))
        asset_points.append({
            "ticker": t,
            "expected_return": float(mu[i]),
            "volatility": sigma_i,
        })

    current_desc: Optional[Dict[str, Any]] = None
    if current_w_aligned is not None and current_w_aligned.size == len(available):
        current_desc = _build_portfolio_descriptor(current_w_aligned, available, mu, cov, rf)

    out = {
        "tickers": available,
        "risk_free_rate": rf,
        "observations": int(len(log_rets)),
        "start_date_used": log_rets.index[0].date().isoformat(),
        "end_date_used": log_rets.index[-1].date().isoformat(),
        "frontier": frontier_points,
        "assets": asset_points,
        "min_variance": minvar_desc,
        "max_sharpe": tangent_desc,
        "current_portfolio": current_desc,
        "errors": errors,
    }
    EF_CACHE[cache_key] = out
    return out


@router.post("/yahoo/efficient-frontier", response_model=EfficientFrontierResponse)
def yahoo_efficient_frontier_post(req: EfficientFrontierRequest):
    try:
        return _run_efficient_frontier(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            risk_free_rate=req.risk_free_rate,
            n_points=req.n_points,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================
# Black-Litterman model
# =========================

def _optimize_with_bounds(
    objective,
    n: int,
    max_weight: float = 1.0,
    min_weight: float = 0.0,
) -> Optional[np.ndarray]:
    """Long-only, fully-invested optimizer with min/max weight per asset.

    Clamps bounds so a feasible sum(w)=1 always exists (n*lo <= 1 <= n*cap).
    """
    lo = min(float(min_weight), 1.0 / n)
    cap = max(min(float(max_weight), 1.0), 1.0 / n)
    cap = max(cap, lo)
    w0 = np.full(n, 1.0 / n)
    bounds = [(lo, cap)] * n
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]
    res = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 300, "ftol": 1e-10, "disp": False},
    )
    return res.x if res.success else None


def _black_litterman_posterior(
    cov: np.ndarray,
    w_mkt: np.ndarray,
    rf: float,
    risk_aversion: float,
    tau: float,
    P: Optional[np.ndarray],
    Q: Optional[np.ndarray],
    confidences: Optional[np.ndarray],
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (implied_returns, posterior_returns), both annualized total returns.

    Implied (equilibrium) returns: Pi = rf + delta * cov @ w_mkt.
    Posterior (master formula): mu_BL = Pi + tauSigma P^T (P tauSigma P^T + Omega)^-1 (Q - P Pi).
    Omega is diagonal, scaled per-view by confidence: higher confidence -> smaller Omega.
    """
    tau_sigma = tau * cov
    implied = rf + risk_aversion * (cov @ w_mkt)

    if P is None or Q is None or P.shape[0] == 0:
        return implied, implied.copy()

    # Base view uncertainty proportional to the view portfolio's variance.
    base = P @ tau_sigma @ P.T                      # k x k
    diag = np.clip(np.diag(base), 1e-12, None)
    c = np.clip(confidences, 1e-2, 0.99)
    # confidence 0.5 -> Omega == base variance; higher confidence -> smaller Omega
    omega_diag = diag * (1.0 - c) / c
    omega = np.diag(omega_diag)

    middle = P @ tau_sigma @ P.T + omega
    try:
        inv_middle = np.linalg.inv(middle)
    except np.linalg.LinAlgError:
        inv_middle = np.linalg.pinv(middle)

    adjustment = tau_sigma @ P.T @ inv_middle @ (Q - P @ implied)
    posterior = implied + adjustment
    return implied, posterior


def _run_black_litterman(
    tickers: List[str],
    prior_weights: Optional[List[float]],
    views: List[Any],
    lookback_period: str,
    auto_adjust: bool,
    risk_free_rate: float,
    risk_aversion: float,
    tau: float,
    max_weight: float,
    min_weight: float,
) -> Dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required for the Black-Litterman model")

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    # Normalize prior (market) weights aligned to the input ticker order.
    prior_arr: Optional[np.ndarray] = None
    if prior_weights is not None:
        if len(prior_weights) != len(tickers):
            raise ValueError("prior_weights length must match tickers length")
        pw = np.array(prior_weights, dtype=float)
        if np.any(pw < 0):
            raise ValueError("prior_weights must be non-negative")
        s = pw.sum()
        if s > 0:
            prior_arr = pw / s

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: Dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    if len(available) < 2:
        raise ValueError("Need at least 2 tickers with price data for Black-Litterman")

    # Re-align prior weights to available tickers (renormalize); default equal weights.
    if prior_arr is not None:
        keep_mask = np.array([t in close.columns for t in tickers])
        w_kept = prior_arr[keep_mask]
        sk = w_kept.sum()
        w_mkt = (w_kept / sk) if sk > 0 else np.full(len(available), 1.0 / len(available))
    else:
        w_mkt = np.full(len(available), 1.0 / len(available))

    prices = close[available].dropna(how="any")
    if len(prices) < 30:
        raise ValueError("Not enough overlapping price observations (need >= 30)")

    log_rets = np.log(prices / prices.shift(1)).dropna()
    if len(log_rets) < 20:
        raise ValueError("Not enough return observations for Black-Litterman")

    ann_factor = 252.0
    cov = log_rets.cov().to_numpy() * ann_factor                # annualized
    rf = float(risk_free_rate)

    idx = {t: i for i, t in enumerate(available)}

    # Build the picking matrix P and view vector Q from the user's views.
    rows: List[np.ndarray] = []
    q_vals: List[float] = []
    conf_vals: List[float] = []
    warnings: List[str] = []
    for v in views:
        vtype = getattr(v, "view_type", "absolute")
        asset = getattr(v, "asset", None)
        if asset not in idx:
            warnings.append(f"View skipped: '{asset}' has no price data")
            continue
        row = np.zeros(len(available))
        if vtype == "relative":
            other = getattr(v, "asset_other", None)
            if other not in idx:
                warnings.append(f"Relative view skipped: '{other}' has no price data")
                continue
            if other == asset:
                warnings.append(f"Relative view skipped: '{asset}' compared with itself")
                continue
            row[idx[asset]] = 1.0
            row[idx[other]] = -1.0
        else:
            row[idx[asset]] = 1.0
        rows.append(row)
        q_vals.append(float(getattr(v, "value")))
        conf_vals.append(float(getattr(v, "confidence", 0.5)))

    if rows:
        P = np.vstack(rows)
        Q = np.array(q_vals, dtype=float)
        confidences = np.array(conf_vals, dtype=float)
    else:
        P = None
        Q = None
        confidences = None

    implied, posterior = _black_litterman_posterior(
        cov=cov, w_mkt=w_mkt, rf=rf, risk_aversion=float(risk_aversion),
        tau=float(tau), P=P, Q=Q, confidences=confidences,
    )

    n = len(available)

    # Optimal (max-Sharpe on posterior returns) with min/max weight bounds.
    def neg_sharpe(w):
        ret = float(np.dot(w, posterior))
        var = float(w @ cov @ w)
        vol = float(np.sqrt(max(var, 1e-18)))
        return -(ret - rf) / vol if vol > 0 else 0.0

    w_opt = _optimize_with_bounds(neg_sharpe, n, max_weight, min_weight)
    if w_opt is None:
        warnings.append("Max-Sharpe optimization did not converge; using equal weights")
        w_opt = np.full(n, 1.0 / n)

    w_minvar = _optimize_with_bounds(lambda w: float(w @ cov @ w), n, max_weight, min_weight)
    if w_minvar is None:
        w_minvar = np.full(n, 1.0 / n)

    optimal_desc = _build_portfolio_descriptor(w_opt, available, posterior, cov, rf)
    minvar_desc = _build_portfolio_descriptor(w_minvar, available, posterior, cov, rf)

    asset_points: List[Dict[str, Any]] = []
    for i, t in enumerate(available):
        asset_points.append({
            "ticker": t,
            "prior_return": float(implied[i]),
            "posterior_return": float(posterior[i]),
            "volatility": float(np.sqrt(max(cov[i, i], 0.0))),
            "prior_weight": float(w_mkt[i]),
            "optimal_weight": float(w_opt[i]),
        })

    out = {
        "tickers": available,
        "risk_free_rate": rf,
        "risk_aversion": float(risk_aversion),
        "tau": float(tau),
        "observations": int(len(log_rets)),
        "start_date_used": log_rets.index[0].date().isoformat(),
        "end_date_used": log_rets.index[-1].date().isoformat(),
        "assets": asset_points,
        "prior_weights": {available[i]: float(w_mkt[i]) for i in range(n)},
        "implied_returns": {available[i]: float(implied[i]) for i in range(n)},
        "posterior_returns": {available[i]: float(posterior[i]) for i in range(n)},
        "optimal": optimal_desc,
        "min_variance": minvar_desc,
        "n_views_applied": 0 if P is None else int(P.shape[0]),
        "warnings": warnings,
        "errors": errors,
    }
    return out


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
        out = _run_black_litterman(
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
        raise HTTPException(status_code=400, detail=str(e))
    BL_CACHE[cache_key] = out
    return out


# =========================
# Random portfolio sampler (top-K by composite return/risk + diversification)
# =========================

def _avg_off_diag_correlation(corr_mat: np.ndarray) -> float:
    n = corr_mat.shape[0]
    if n < 2:
        return 0.0
    iu = np.triu_indices(n, k=1)
    vals = corr_mat[iu]
    return float(np.nanmean(vals)) if vals.size else 0.0


def _optimize_subset(
    mu_sub: np.ndarray,
    cov_sub: np.ndarray,
    rf: float,
    mode: str,
    max_weight: float = 1.0,
    min_weight: float = 0.0,
) -> Optional[np.ndarray]:
    n = len(mu_sub)
    if mode == "equal_weight":
        return np.full(n, 1.0 / n)

    # max_sharpe — clamp lo so n*lo <= 1 (feasibility guarantee)
    lo = min(float(min_weight), 1.0 / n)
    cap = max(min(float(max_weight), 1.0), lo)
    w0 = np.full(n, 1.0 / n)
    bounds = [(lo, cap)] * n
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]

    def neg_sharpe(w):
        ret = float(np.dot(w, mu_sub))
        var = float(w @ cov_sub @ w)
        vol = float(np.sqrt(max(var, 1e-18)))
        return -(ret - rf) / vol if vol > 0 else 0.0

    res = minimize(
        neg_sharpe, w0, method="SLSQP",
        bounds=bounds, constraints=constraints,
        options={"maxiter": 150, "ftol": 1e-9, "disp": False},
    )
    return res.x if res.success else None


def _run_portfolio_sampler(
    tickers: List[str],
    portfolio_size: int,
    n_simulations: int,
    top_k: int,
    lookback_period: str,
    auto_adjust: bool,
    risk_free_rate: float,
    diversification_weight: float,
    max_weight: float,
    min_weight: float,
    optimization: str,
    seed: int,
) -> Dict[str, Any]:
    # de-dup tickers while preserving order
    seen: set = set()
    uniq_tickers: List[str] = []
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            uniq_tickers.append(t)

    if len(uniq_tickers) < portfolio_size:
        raise ValueError(
            f"Need at least {portfolio_size} unique tickers in the universe (got {len(uniq_tickers)})"
        )

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    cache_key = (
        "sampler",
        tuple(uniq_tickers),
        int(portfolio_size),
        int(n_simulations),
        int(top_k),
        lookback_period,
        auto_adjust,
        round(float(risk_free_rate), 6),
        round(float(diversification_weight), 6),
        round(float(max_weight), 6),
        round(float(min_weight), 6),
        optimization,
        int(seed),
        end_ts.date().isoformat(),
    )
    if cache_key in SAMPLER_CACHE:
        return SAMPLER_CACHE[cache_key]

    close = _download_close_daily_multi(uniq_tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in uniq_tickers if t in close.columns]
    errors: Dict[str, str] = {
        t: "Ticker not found in downloaded data"
        for t in uniq_tickers if t not in close.columns
    }
    if len(available) < portfolio_size:
        raise ValueError(
            f"Only {len(available)} tickers have price data, need at least {portfolio_size}"
        )

    # Drop tickers with too few observations on their own
    raw = close[available]
    # Compute per-ticker observation count after dropping NaNs on each column
    valid_tickers = [t for t in available if raw[t].dropna().shape[0] >= 60]
    if len(valid_tickers) < portfolio_size:
        raise ValueError(
            f"Only {len(valid_tickers)} tickers have >=60 daily observations, need {portfolio_size}"
        )
    extra_drop = set(available) - set(valid_tickers)
    for t in extra_drop:
        errors[t] = "Less than 60 daily observations"

    # Precompute log-returns for the full universe (per-ticker NaNs preserved)
    prices_full = close[valid_tickers]
    log_rets_full = np.log(prices_full / prices_full.shift(1))

    ann_factor = 252.0
    rng = np.random.default_rng(seed)
    n_universe = len(valid_tickers)

    drawn_combos: set = set()
    cloud: List[Dict[str, float]] = []
    portfolios: List[Dict[str, Any]] = []
    n_failed = 0

    # Hard ceiling on draws to avoid infinite loops if dedup keeps colliding
    max_attempts = max(n_simulations * 5, 100)
    attempts = 0

    while len(cloud) + n_failed < n_simulations and attempts < max_attempts:
        attempts += 1
        idx = rng.choice(n_universe, size=portfolio_size, replace=False)
        idx_key = frozenset(int(i) for i in idx)
        if idx_key in drawn_combos:
            continue
        drawn_combos.add(idx_key)

        sub_tickers = [valid_tickers[i] for i in idx]
        sub_rets = log_rets_full[sub_tickers].dropna(how="any")
        if len(sub_rets) < 20:
            n_failed += 1
            continue

        mu_sub = sub_rets.mean().to_numpy() * ann_factor
        cov_sub = sub_rets.cov().to_numpy() * ann_factor

        w = _optimize_subset(mu_sub, cov_sub, float(risk_free_rate), optimization, float(max_weight), float(min_weight))
        if w is None:
            n_failed += 1
            continue

        ret = float(np.dot(w, mu_sub))
        var = float(w @ cov_sub @ w)
        vol = float(np.sqrt(max(var, 0.0)))
        sharpe = ((ret - float(risk_free_rate)) / vol) if vol > 0 else 0.0

        corr_mat = sub_rets.corr().to_numpy()
        avg_corr = _avg_off_diag_correlation(corr_mat)

        composite = float(sharpe - float(diversification_weight) * avg_corr)

        cloud.append({
            "volatility": vol,
            "expected_return": ret,
            "sharpe": sharpe,
            "avg_correlation": avg_corr,
            "composite_score": composite,
            "tickers": sub_tickers,
            "weights": [float(x) for x in w.tolist()],
        })
        portfolios.append({
            "tickers": sub_tickers,
            "weights": [float(x) for x in w.tolist()],
            "expected_return": ret,
            "volatility": vol,
            "sharpe": sharpe,
            "avg_correlation": avg_corr,
            "composite_score": composite,
        })

    if not portfolios:
        raise ValueError("No valid portfolio could be evaluated")

    top_composite = sorted(portfolios, key=lambda p: p["composite_score"], reverse=True)[:top_k]
    top_sharpe = sorted(portfolios, key=lambda p: p["sharpe"], reverse=True)[:top_k]

    out = {
        "universe": valid_tickers,
        "portfolio_size": int(portfolio_size),
        "n_simulations_requested": int(n_simulations),
        "n_simulations_evaluated": int(len(portfolios)),
        "n_simulations_failed": int(n_failed),
        "observations": int(log_rets_full.dropna(how="any").shape[0]),
        "start_date_used": prices_full.dropna(how="all").index[0].date().isoformat(),
        "end_date_used": prices_full.dropna(how="all").index[-1].date().isoformat(),
        "risk_free_rate": float(risk_free_rate),
        "diversification_weight": float(diversification_weight),
        "optimization": optimization,
        "top_by_composite": top_composite,
        "top_by_sharpe": top_sharpe,
        "cloud": cloud,
        "errors": errors,
    }
    SAMPLER_CACHE[cache_key] = out
    return out


@router.post("/yahoo/portfolio-sampler", response_model=PortfolioSamplerResponse)
def yahoo_portfolio_sampler_post(req: PortfolioSamplerRequest):
    try:
        return _run_portfolio_sampler(
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
        raise HTTPException(status_code=400, detail=str(e))


# =========================
# PCA — eigen decomposition of the variance-covariance matrix
# =========================
#
# The portfolio variance decomposes exactly over the eigenbasis of the covariance
# matrix. With Sigma = V L V' (L diagonal, V orthonormal) and y = V'w:
#
#     sigma_p^2 = w' Sigma w = y' L y = sum_i lambda_i * y_i^2
#
# Each term is non-negative, so `lambda_i * y_i^2` is *the* contribution of
# principal component i to the portfolio variance. A large eigenvalue only hurts
# if the portfolio is actually exposed to that direction (y_i != 0) — which is
# exactly what this endpoint separates.
#
# In "correlation" mode the matrix diagonalized is R (= D^-1 Sigma D^-1). Since
# Sigma = D R D, using vol-scaled weights w~ = D w keeps the identity exact:
#     sigma_p^2 = w~' R w~ = sum_i lambda_i * (v_i' w~)^2


def _pc_sign_normalized(vec: np.ndarray) -> np.ndarray:
    """Eigenvectors are sign-arbitrary. Orient so the dominant direction is positive,
    which makes 'all loadings same sign' readable as a common market move."""
    s = float(np.sum(vec))
    if abs(s) > 1e-9:
        return vec if s > 0 else -vec
    # Balanced spread: anchor on the largest absolute loading instead.
    k = int(np.argmax(np.abs(vec)))
    return vec if vec[k] >= 0 else -vec


def _pc_interpretation(
    vec: np.ndarray,
    explained_ratio: float,
    contribution_pct: float,
    top_pos: List[str],
    top_neg: List[str],
    index: int,
) -> str:
    n_pos = int(np.sum(vec > 1e-6))
    n_neg = int(np.sum(vec < -1e-6))
    dominant = top_pos or top_neg

    if n_pos == 0 or n_neg == 0:
        if index == 1:
            base = ("Common market direction — every holding moves together. "
                    "This is your undiversifiable core risk.")
        elif dominant:
            base = "Broad co-movement of " + ", ".join(dominant) + "."
        else:
            base = "Broad co-movement across the holdings."
    else:
        base = ("Spread: " + ", ".join(top_pos) + " up against " + ", ".join(top_neg) + " down. "
                "A relative-value / rotation factor.")

    if contribution_pct >= 0.5:
        tail = f" Drives {contribution_pct * 100:.0f}% of your portfolio variance."
    elif contribution_pct >= 0.15:
        tail = f" Contributes {contribution_pct * 100:.0f}% of your portfolio variance."
    elif explained_ratio >= 0.10 and contribution_pct < 0.05:
        tail = (f" Present in the market ({explained_ratio * 100:.0f}% of matrix variance) but your "
                f"weights barely touch it ({contribution_pct * 100:.1f}% of your variance) — "
                f"a risk you are already netting out.")
    else:
        tail = f" Minor: {contribution_pct * 100:.1f}% of your portfolio variance."

    return base + tail


def _run_pca_risk(
    tickers: List[str],
    weights: Optional[List[float]],
    lookback_period: str,
    auto_adjust: bool,
    return_mode: ReturnMode,
    matrix_type: PCAMatrixType,
    n_components: int,
    top_loadings: int,
) -> Dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required to run a PCA risk decomposition")

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    w_in: Optional[np.ndarray] = None
    if weights is not None:
        if len(weights) != len(tickers):
            raise ValueError("weights length must match tickers length")
        w_in = np.array(weights, dtype=float)
        if np.any(w_in < 0):
            raise ValueError("weights must be non-negative")
        if w_in.sum() <= 0:
            raise ValueError("sum of weights must be > 0")
        w_in = w_in / w_in.sum()

    cache_key = (
        "pca",
        tuple(tickers),
        None if w_in is None else tuple(round(float(x), 6) for x in w_in.tolist()),
        lookback_period,
        auto_adjust,
        return_mode,
        matrix_type,
        int(n_components),
        int(top_loadings),
        end_ts.date().isoformat(),
    )
    if cache_key in PCA_CACHE:
        return PCA_CACHE[cache_key]

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: Dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    if len(available) < 2:
        raise ValueError("Need at least 2 tickers with price data to run a PCA")

    # Re-align weights to the tickers that actually have data (renormalize); default equal.
    if w_in is not None:
        keep_mask = np.array([t in close.columns for t in tickers])
        w_kept = w_in[keep_mask]
        sk = w_kept.sum()
        w = (w_kept / sk) if sk > 0 else np.full(len(available), 1.0 / len(available))
    else:
        w = np.full(len(available), 1.0 / len(available))

    prices = close[available].dropna(how="any")
    if len(prices) < 30:
        raise ValueError("Not enough overlapping price observations (need >= 30)")

    if return_mode == "log":
        rets = np.log(prices / prices.shift(1)).dropna()
    else:
        rets = prices.pct_change().dropna()

    if len(rets) < 20:
        raise ValueError("Not enough return observations to run a PCA")

    n = len(available)
    warnings: List[str] = []
    if len(rets) < n:
        warnings.append(
            f"Only {len(rets)} observations for {n} assets — the covariance matrix is singular, "
            f"so the smallest eigenvalues are noise. Use a longer lookback."
        )

    ann_factor = 252.0
    cov = rets.cov().to_numpy() * ann_factor                 # annualized variance-covariance
    cov = (cov + cov.T) / 2.0                                # enforce exact symmetry
    vols = np.sqrt(np.clip(np.diag(cov), 0.0, None))

    if matrix_type == "correlation":
        safe_vols = np.where(vols > 1e-12, vols, 1.0)
        d_inv = np.diag(1.0 / safe_vols)
        target = d_inv @ cov @ d_inv
        target = (target + target.T) / 2.0
        np.fill_diagonal(target, 1.0)
        w_eff = w * vols                                     # vol-scaled weights keep the identity exact
    else:
        target = cov
        w_eff = w

    # eigh: symmetric matrices -> real eigenvalues, orthonormal eigenvectors (ascending).
    eigvals, eigvecs = np.linalg.eigh(target)
    order = np.argsort(eigvals)[::-1]                        # descending: PC1 first
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    # Tiny negatives are floating-point noise on a PSD matrix.
    eigvals = np.where(np.abs(eigvals) < 1e-14, 0.0, eigvals)
    if np.any(eigvals < 0):
        warnings.append("Some eigenvalues are slightly negative (numerical noise); clipped to zero.")
        eigvals = np.clip(eigvals, 0.0, None)

    trace = float(np.sum(eigvals))
    if trace <= 0:
        raise ValueError("Degenerate covariance matrix (zero total variance)")

    # Portfolio coordinates in the eigenbasis and the exact variance split.
    exposures = eigvecs.T @ w_eff                            # y_i
    contributions = eigvals * (exposures ** 2)               # lambda_i * y_i^2, all >= 0
    port_var = float(np.sum(contributions))
    port_vol = float(np.sqrt(max(port_var, 0.0)))
    if port_var <= 0:
        raise ValueError("Portfolio variance is zero — check weights and price data")

    contrib_pct = contributions / port_var
    explained = eigvals / trace
    cum_explained = np.cumsum(explained)
    cum_contrib = np.cumsum(contrib_pct)

    def _first_index_reaching(cum: np.ndarray, threshold: float) -> int:
        hits = np.nonzero(cum >= threshold)[0]
        return int(hits[0]) + 1 if hits.size else int(cum.size)

    # Effective number of bets (Meucci): entropy of the variance contributions.
    p = contrib_pct[contrib_pct > 1e-12]
    enb = float(np.exp(-np.sum(p * np.log(p)))) if p.size else 1.0

    pos_eig = eigvals[eigvals > 1e-12]
    condition_number = float(pos_eig[0] / pos_eig[-1]) if pos_eig.size >= 2 else 1.0

    k = min(int(n_components), n)
    components: List[Dict[str, Any]] = []
    normalized_vecs: List[np.ndarray] = []
    for i in range(n):
        vec = _pc_sign_normalized(eigvecs[:, i].copy())
        normalized_vecs.append(vec)

    for i in range(k):
        vec = normalized_vecs[i]
        # Sign-normalizing the vector flips the exposure sign with it (y = v'w).
        exposure = float(np.dot(vec, w_eff))

        ranked = np.argsort(vec)[::-1]
        top_pos = [available[j] for j in ranked[:top_loadings] if vec[j] > 1e-6]
        top_neg = [available[j] for j in ranked[::-1][:top_loadings] if vec[j] < -1e-6]

        components.append({
            "index": i + 1,
            "eigenvalue": float(eigvals[i]),
            "factor_volatility": float(np.sqrt(max(eigvals[i], 0.0))),
            "explained_variance_ratio": float(explained[i]),
            "cumulative_explained": float(cum_explained[i]),
            "portfolio_exposure": exposure,
            "variance_contribution": float(contributions[i]),
            "variance_contribution_pct": float(contrib_pct[i]),
            "cumulative_variance_contribution_pct": float(cum_contrib[i]),
            "risk_contribution": float(contributions[i] / port_vol),
            "loadings": {available[j]: float(vec[j]) for j in range(n)},
            "top_positive": top_pos,
            "top_negative": top_neg,
            "interpretation": _pc_interpretation(
                vec=vec,
                explained_ratio=float(explained[i]),
                contribution_pct=float(contrib_pct[i]),
                top_pos=top_pos,
                top_neg=top_neg,
                index=i + 1,
            ),
        })

    # Classic per-asset risk attribution, as a cross-check on the eigen view.
    sigma_w = cov @ w
    mctr = sigma_w / port_vol
    ctr = w * mctr                                           # sums to sigma_p
    pc1 = normalized_vecs[0]
    pc1_var_share = eigvals[0] * (pc1 ** 2)                  # PC1 variance carried by each asset
    if matrix_type == "correlation":
        # In correlation space each asset has unit variance.
        denom = np.ones(n)
    else:
        denom = np.where(np.diag(cov) > 1e-18, np.diag(cov), 1.0)

    loading_matrix = np.column_stack(normalized_vecs)        # n x n, columns = PCs
    # Which PC carries most of each asset's variance: lambda_i * v_ij^2.
    per_asset_pc_var = (loading_matrix ** 2) * eigvals[np.newaxis, :]
    top_component = np.argmax(per_asset_pc_var, axis=1) + 1

    assets: List[Dict[str, Any]] = []
    for j, t in enumerate(available):
        assets.append({
            "ticker": t,
            "weight": float(w[j]),
            "volatility": float(vols[j]),
            "marginal_contribution_to_risk": float(mctr[j]),
            "contribution_to_risk": float(ctr[j]),
            "contribution_to_risk_pct": float(ctr[j] / port_vol) if port_vol > 0 else 0.0,
            "pc1_loading": float(pc1[j]),
            "pc1_communality": float(min(1.0, max(0.0, pc1_var_share[j] / denom[j]))),
            "top_component": int(top_component[j]),
        })

    weighted_avg_vol = float(np.dot(w, vols))
    diversification_ratio = float(weighted_avg_vol / port_vol) if port_vol > 0 else 1.0

    out = {
        "tickers": available,
        "weights": [float(x) for x in w.tolist()],
        "matrix_type": matrix_type,
        "return_mode": return_mode,
        "observations": int(len(rets)),
        "start_date_used": rets.index[0].date().isoformat(),
        "end_date_used": rets.index[-1].date().isoformat(),
        "covariance": [[float(v) for v in row] for row in cov],
        "matrix": [[float(v) for v in row] for row in target],
        "components": components,
        "assets": assets,
        "stats": {
            "portfolio_volatility": port_vol,
            "portfolio_variance": port_var,
            "total_matrix_variance": trace,
            "pc1_explained_ratio": float(explained[0]),
            "pc1_variance_contribution_pct": float(contrib_pct[0]),
            "n_components_for_80_matrix": _first_index_reaching(cum_explained, 0.80),
            "n_components_for_90_matrix": _first_index_reaching(cum_explained, 0.90),
            "n_components_for_90_portfolio_risk": _first_index_reaching(cum_contrib, 0.90),
            "effective_number_of_bets": enb,
            "max_contribution_pct": float(np.max(contrib_pct)),
            "diversification_ratio": diversification_ratio,
            "weighted_avg_volatility": weighted_avg_vol,
            "condition_number": condition_number,
        },
        "warnings": warnings,
        "errors": errors,
    }
    PCA_CACHE[cache_key] = out
    return out


@router.post("/yahoo/pca-risk", response_model=PCARiskResponse)
def yahoo_pca_risk_post(req: PCARiskRequest):
    try:
        return _run_pca_risk(
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
        raise HTTPException(status_code=400, detail=str(e))

# =========================
# Portfolio VaR / ES
# =========================

def _overlapping_horizon_returns(rets: np.ndarray, horizon: int) -> np.ndarray:
    """
    Compound simple returns over rolling (overlapping) windows of `horizon` days.
    rets shape (n, k) -> (n - horizon + 1, k). Weights are held fixed over each
    window, so the portfolio horizon return stays exactly the weighted sum of the
    asset horizon returns.
    """
    if horizon <= 1:
        return rets
    growth = np.cumprod(1.0 + rets, axis=0)
    growth = np.vstack([np.ones((1, rets.shape[1])), growth])
    return growth[horizon:] / growth[:-horizon] - 1.0


def _run_portfolio_var_es(
    tickers: List[str],
    weights: Optional[List[float]],
    lookback_period: str,
    auto_adjust: bool,
    confidence_levels: List[float],
    horizon_days: int,
    portfolio_value: Optional[float],
) -> Dict[str, Any]:
    if not tickers:
        raise ValueError("At least one ticker is required")

    horizon = int(horizon_days)
    if horizon < 1:
        raise ValueError("horizon_days must be >= 1")

    cls: List[float] = []
    for a in confidence_levels:
        if not (0.5 < float(a) < 1.0):
            raise ValueError("confidence_levels must be in (0.5, 1.0)")
        cls.append(float(a))
    if not cls:
        raise ValueError("At least one confidence level is required")
    cls = sorted(set(cls))

    w_in: Optional[np.ndarray] = None
    if weights is not None:
        if len(weights) != len(tickers):
            raise ValueError("weights length must match tickers length")
        w_in = np.array(weights, dtype=float)
        if np.any(w_in < 0):
            raise ValueError("weights must be non-negative")
        if w_in.sum() <= 0:
            raise ValueError("sum of weights must be > 0")
        w_in = w_in / w_in.sum()

    days = _PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    cache_key = (
        "portfolio_var_es",
        tuple(tickers),
        None if w_in is None else tuple(round(float(x), 6) for x in w_in.tolist()),
        lookback_period,
        auto_adjust,
        tuple(cls),
        horizon,
        None if portfolio_value is None else round(float(portfolio_value), 2),
        end_ts.date().isoformat(),
    )
    if cache_key in PORTVAR_CACHE:
        return PORTVAR_CACHE[cache_key]

    close = _download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    errors: Dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    # Yahoo hands back an all-NaN column for a symbol it does not know: drop it instead
    # of letting it wipe the overlapping window for every other holding.
    available = []
    for t in tickers:
        if t not in close.columns:
            continue
        if close[t].dropna().empty:
            errors[t] = "No price data returned for ticker"
            continue
        available.append(t)
    if not available:
        raise ValueError("No tickers available in downloaded data")

    # Re-align weights to the tickers that actually have data (renormalize); default equal.
    if w_in is not None:
        keep_mask = np.array([t in available for t in tickers])
        w_kept = w_in[keep_mask]
        s_kept = w_kept.sum()
        if s_kept <= 0:
            raise ValueError("All weights map to missing tickers")
        w = w_kept / s_kept
    else:
        w = np.full(len(available), 1.0 / len(available))

    prices = close[available].dropna(how="any")
    if len(prices) < 30:
        raise ValueError("Not enough overlapping price observations (need >= 30)")

    # VaR is the loss on a linear position, so arithmetic returns are the right space.
    asset_rets = prices.pct_change().dropna(how="any")
    if len(asset_rets) < 20:
        raise ValueError("Not enough return observations to compute portfolio risk")

    daily = asset_rets.to_numpy()
    if len(daily) - horizon + 1 < 20:
        raise ValueError(
            f"Not enough observations for a {horizon}-day horizon "
            f"({len(daily)} daily returns) — use a longer lookback"
        )

    horizon_rets = _overlapping_horizon_returns(daily, horizon)
    horizon_index = asset_rets.index[horizon - 1:]
    port = horizon_rets @ w                                  # exactly additive in the assets
    port_series = pd.Series(port, index=horizon_index)

    warnings: List[str] = []
    n_obs = int(len(port))
    if horizon > 1:
        warnings.append(
            f"Overlapping {horizon}-day windows: {n_obs} observations carry only "
            f"~{max(1, n_obs // horizon)} independent ones, so the tail estimate is noisier "
            f"than the observation count suggests."
        )
    for a in cls:
        expected_tail = n_obs * (1.0 - a)
        if expected_tail < 10:
            warnings.append(
                f"Only ~{expected_tail:.0f} observations sit beyond the "
                f"{a * 100:.0f}% threshold — the historical VaR/ES at that level rests on very "
                f"few points. Use a longer lookback or a lower confidence level."
            )

    # Annualized standalone / portfolio volatilities from the daily returns
    ann_factor = 252.0
    daily_vols = np.std(daily, axis=0, ddof=1)
    vols_ann = daily_vols * np.sqrt(ann_factor)
    port_daily = daily @ w
    port_vol_ann = float(np.std(port_daily, ddof=1) * np.sqrt(ann_factor))
    weighted_avg_vol = float(np.dot(w, vols_ann))
    diversification_ratio = (weighted_avg_vol / port_vol_ann) if port_vol_ann > 0 else 0.0

    # Covariance of the horizon returns: drives the Gaussian decomposition
    cov_h = np.atleast_2d(np.cov(horizon_rets, rowvar=False, ddof=1))
    cov_h = (cov_h + cov_h.T) / 2.0
    mu_h = horizon_rets.mean(axis=0)
    cov_w = cov_h @ w
    port_var_h = float(w @ cov_w)
    sigma_p = float(np.sqrt(max(port_var_h, 0.0)))

    pv = float(portfolio_value) if portfolio_value else 0.0

    points: List[Dict[str, Any]] = []
    for alpha in cls:
        summary = es_summary(port_series, [alpha])[0]

        z = float(norm.ppf(1 - alpha))                       # negative (left tail)

        # Historical tail days: the ES decomposition below sums exactly to es_historical
        q = float(np.quantile(port, 1 - alpha))
        tail_mask = port <= q
        tail_means = (horizon_rets[tail_mask].mean(axis=0)
                      if tail_mask.any() else np.zeros(len(available)))

        es_hist = summary["es_historical"]
        var_gauss = summary["var_gaussian"]

        contributions: List[Dict[str, Any]] = []
        undiversified = 0.0
        for i, t in enumerate(available):
            standalone = var_historical(pd.Series(horizon_rets[:, i]), alpha)
            undiversified += float(w[i]) * standalone

            if sigma_p > 0:
                marginal = -float(mu_h[i]) - z * float(cov_w[i]) / sigma_p
                beta = float(cov_w[i]) / port_var_h
            else:
                marginal = 0.0
                beta = 0.0
            component_var = float(w[i]) * marginal
            component_es = -float(w[i]) * float(tail_means[i])

            contributions.append({
                "ticker": t,
                "weight": float(w[i]),
                "volatility": float(vols_ann[i]),
                "standalone_var": standalone,
                "beta_to_portfolio": beta,
                "marginal_var": marginal,
                "component_var": component_var,
                "component_var_pct": (component_var / var_gauss) if var_gauss != 0 else 0.0,
                "component_es": component_es,
                "component_es_pct": (component_es / es_hist) if es_hist != 0 else 0.0,
            })

        var_hist = summary["var_historical"]
        benefit = undiversified - var_hist

        breaches = int(np.sum(port <= -var_gauss))

        points.append({
            "confidence_level": float(alpha),
            **{k: float(v) for k, v in summary.items() if k != "confidence_level"},
            "var_historical_value": var_hist * pv,
            "es_historical_value": es_hist * pv,
            "var_gaussian_value": var_gauss * pv,
            "es_gaussian_value": summary["es_gaussian"] * pv,
            "var_cornish_fisher_value": summary["var_cornish_fisher"] * pv,
            "es_cf_empirical_tail_value": summary["es_cf_empirical_tail"] * pv,
            "undiversified_var": undiversified,
            "diversification_benefit": benefit,
            "diversification_benefit_pct": (benefit / undiversified) if undiversified > 0 else 0.0,
            "gaussian_breaches": breaches,
            "gaussian_breach_rate": (breaches / n_obs) if n_obs else 0.0,
            "expected_breach_rate": 1.0 - float(alpha),
            "contributions": contributions,
        })

    worst_idx = int(np.argmin(port)) if n_obs else 0

    out = {
        "tickers": available,
        "weights": w.tolist(),
        "lookback_period": lookback_period,
        "return_mode": "arith",
        "horizon_days": horizon,
        "observations": n_obs,
        "start_date_used": horizon_index[0].date().isoformat(),
        "end_date_used": horizon_index[-1].date().isoformat(),
        "price_type": "Adjusted Close" if auto_adjust else "Close",
        "portfolio_value": float(portfolio_value) if portfolio_value else None,
        "stats": {
            "portfolio_volatility": float(np.std(port, ddof=1)) if n_obs > 1 else 0.0,
            "portfolio_volatility_annualized": port_vol_ann,
            "weighted_avg_volatility": weighted_avg_vol,
            "diversification_ratio": diversification_ratio,
            "mean_return": float(np.mean(port)) if n_obs else 0.0,
            "skewness": float(port_series.skew()) if n_obs > 2 else 0.0,
            "excess_kurtosis": float(port_series.kurtosis()) if n_obs > 3 else 0.0,
            "worst_return": float(port[worst_idx]) if n_obs else 0.0,
            "worst_return_date": horizon_index[worst_idx].date().isoformat() if n_obs else "",
            "best_return": float(np.max(port)) if n_obs else 0.0,
        },
        "points": points,
        "warnings": warnings,
        "errors": errors,
    }
    PORTVAR_CACHE[cache_key] = out
    return out


@router.post("/yahoo/portfolio-var-es", response_model=PortfolioVaREsResponse)
def yahoo_portfolio_var_es_post(req: PortfolioVaREsRequest):
    try:
        return _run_portfolio_var_es(
            tickers=req.tickers,
            weights=req.weights,
            lookback_period=req.lookback_period,
            auto_adjust=req.auto_adjust,
            confidence_levels=req.confidence_levels,
            horizon_days=req.horizon_days,
            portfolio_value=req.portfolio_value,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
