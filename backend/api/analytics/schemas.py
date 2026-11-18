"""Request / response schemas of the analytics API."""

from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("must be a valid date in YYYY-MM-DD format") from None


# Date received as a string, validated and normalised to YYYY-MM-DD (invalid dates -> 422, not 500)
IsoDate = Annotated[str, AfterValidator(_iso_date)]


class DateRangeRequest(BaseModel):
    """Base for requests with a start_date / end_date window."""

    @model_validator(mode="after")
    def _check_range(self):
        start, end = getattr(self, "start_date", None), getattr(self, "end_date", None)
        if start and end and start > end:  # ISO strings compare chronologically
            raise ValueError("start_date must be on or before end_date")
        return self

PERIODS = ["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]
Period = Literal["1D", "1W", "1M", "YTD", "1Y", "3Y", "5Y"]

VolFrequency = Literal["daily", "weekly", "monthly"]
ReturnMode = Literal["log", "arith"]


class YahooPerfRow(BaseModel):
    ticker: str
    asof_requested: str | None
    asof_used: str
    last: float
    perf: dict[Period, float | None]


class YahooPerfResponse(BaseModel):
    data: list[YahooPerfRow]
    errors: dict[str, str] = Field(default_factory=dict)


class YahooPerfRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=500)
    asof: IsoDate | None = None
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
    data: list[YahooReturnRow]
    errors: dict[str, str] = Field(default_factory=dict)


class YahooReturnRequest(DateRangeRequest):
    tickers: list[str] = Field(min_length=1, max_length=500)
    start_date: IsoDate  # YYYY-MM-DD
    end_date: IsoDate    # YYYY-MM-DD
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
    points: list[CumReturnPoint]

class YahooCumReturnsResponse(BaseModel):
    data: list[YahooCumReturnsSeries]
    errors: dict[str, str] = Field(default_factory=dict)

class YahooCumReturnsRequest(DateRangeRequest):
    tickers: list[str] = Field(min_length=1, max_length=200)  # full series returned => lower limit
    start_date: IsoDate
    end_date: IsoDate
    auto_adjust: bool = True

class DrawdownEpisode(BaseModel):
    start_date: str
    trough_date: str
    end_date: str | None
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
    recovery_date: str | None
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
    episodes: list[DrawdownEpisode] = Field(default_factory=list)
    series: list[DrawdownPoint] | None = None

class YahooDrawdownResponse(BaseModel):
    data: list[YahooDrawdownRow]
    errors: dict[str, str] = Field(default_factory=dict)

class YahooDrawdownRequest(DateRangeRequest):
    tickers: list[str] = Field(min_length=1, max_length=200)
    start_date: IsoDate
    end_date: IsoDate
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
    data: list[YahooAnnVolRow]
    errors: dict[str, str] = Field(default_factory=dict)


class YahooAnnVolRequest(DateRangeRequest):
    tickers: list[str] = Field(min_length=1, max_length=200)
    start_date: IsoDate
    end_date: IsoDate
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
    points: list[VaREsPoint]


class YahooVaREsResponse(BaseModel):
    data: list[YahooVaREsRow]
    errors: dict[str, str] = Field(default_factory=dict)


class YahooVaREsRequest(DateRangeRequest):
    tickers: list[str] = Field(min_length=1, max_length=200)
    start_date: IsoDate
    end_date: IsoDate
    auto_adjust: bool = True
    return_mode: ReturnMode = "arith"
    confidence_levels: list[float] = Field(default_factory=lambda: [0.95, 0.99], min_length=1, max_length=10)


class YahooAllMetricsResponse(BaseModel):
    perf: YahooPerfResponse | None = None
    vol: YahooAnnVolResponse | None = None
    dd: YahooDrawdownResponse | None = None
    risk: YahooVaREsResponse | None = None
    cum_returns: YahooCumReturnsResponse | None = None


class MonteCarloPercentiles(BaseModel):
    p5: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p95: list[float]


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
    dates: list[str]
    percentiles: MonteCarloPercentiles
    samples: list[list[float]]
    stats: MonteCarloStats
    tickers: list[str]
    weights: list[float]
    errors: dict[str, str] = Field(default_factory=dict)


MONTE_CARLO_MAX_POINTS = 10_000_000


class MonteCarloRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=100)
    weights: list[float] = Field(min_length=1, max_length=100)
    horizon_days: int = Field(default=252, ge=10, le=2520)
    n_simulations: int = Field(default=1000, ge=50, le=20000)
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    seed: int = 42
    n_sample_paths: int = Field(default=30, ge=0, le=200)
    initial_value: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def _check_memory_budget(self):
        # The service keeps every simulated path (n_simulations x horizon_days floats) to compute
        # percentiles: cap it so a single request stays around 80 MB instead of up to 400 MB+.
        if self.n_simulations * self.horizon_days > MONTE_CARLO_MAX_POINTS:
            raise ValueError(
                f"n_simulations x horizon_days must not exceed {MONTE_CARLO_MAX_POINTS:,} "
                f"(e.g. 20,000 simulations over 500 days, or 4,000 over 2,520 days)"
            )
        return self


class CorrelationPair(BaseModel):
    ticker_a: str
    ticker_b: str
    correlation: float


class CorrelationStats(BaseModel):
    avg_correlation: float                # mean of upper-triangle (off-diagonal) values
    weighted_avg_correlation: float | None = None  # weighted by w_i * w_j on off-diagonal
    min_pair: CorrelationPair | None = None
    max_pair: CorrelationPair | None = None
    pct_pairs_above_0_7: float            # share of pairs with corr > 0.7
    pct_pairs_below_0_3: float            # share of pairs with corr < 0.3
    diversification_score: float          # 1 - avg_correlation (clamped to [0,1])
    n_pairs: int


class CorrelationResponse(BaseModel):
    tickers: list[str]
    matrix: list[list[float]]             # square matrix, indexed by tickers
    observations: int
    start_date_used: str
    end_date_used: str
    stats: CorrelationStats
    errors: dict[str, str] = Field(default_factory=dict)


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
    tickers: list[str]
    weights: list[float]
    observations: int
    start_date_used: str
    end_date_used: str
    risk_free_rate: float
    stats: PortfolioHealthStats
    errors: dict[str, str] = Field(default_factory=dict)


class FrontierPoint(BaseModel):
    expected_return: float
    volatility: float
    sharpe: float


class PortfolioOnFrontier(BaseModel):
    weights: dict[str, float]
    expected_return: float
    volatility: float
    sharpe: float


class AssetPoint(BaseModel):
    ticker: str
    expected_return: float
    volatility: float


class EfficientFrontierResponse(BaseModel):
    tickers: list[str]
    risk_free_rate: float
    observations: int
    start_date_used: str
    end_date_used: str
    frontier: list[FrontierPoint]
    assets: list[AssetPoint]
    min_variance: PortfolioOnFrontier
    max_sharpe: PortfolioOnFrontier
    current_portfolio: PortfolioOnFrontier | None = None
    errors: dict[str, str] = Field(default_factory=dict)


SamplerOptimization = Literal["max_sharpe", "equal_weight"]


class SampledPortfolio(BaseModel):
    tickers: list[str]
    weights: list[float]
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
    tickers: list[str]
    weights: list[float]


class PortfolioSamplerResponse(BaseModel):
    universe: list[str]
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
    top_by_composite: list[SampledPortfolio]
    top_by_sharpe: list[SampledPortfolio]
    cloud: list[SamplerCloudPoint]
    errors: dict[str, str] = Field(default_factory=dict)


class PortfolioSamplerRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=300)
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
    tickers: list[str] = Field(min_length=2, max_length=50)
    weights: list[float] | None = Field(default=None, max_length=100)
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
    asset_other: str | None = None
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
    tickers: list[str]
    risk_free_rate: float
    risk_aversion: float
    tau: float
    observations: int
    start_date_used: str
    end_date_used: str
    assets: list[BLAssetPoint]
    prior_weights: dict[str, float]
    implied_returns: dict[str, float]
    posterior_returns: dict[str, float]
    optimal: PortfolioOnFrontier          # max-Sharpe on posterior returns
    min_variance: PortfolioOnFrontier
    n_views_applied: int
    warnings: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)


class BlackLittermanRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=50)
    prior_weights: list[float] | None = Field(default=None, max_length=100)             # market / equilibrium weights; default equal
    views: list[BLView] = Field(default_factory=list)
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
    loadings: dict[str, float]                      # ticker -> eigenvector coefficient
    top_positive: list[str]
    top_negative: list[str]
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
    tickers: list[str]
    weights: list[float]
    matrix_type: PCAMatrixType
    return_mode: ReturnMode
    observations: int
    start_date_used: str
    end_date_used: str
    covariance: list[list[float]]                   # annualized variance-covariance matrix
    matrix: list[list[float]]                       # the matrix actually diagonalized
    components: list[PCAComponent]
    assets: list[PCAAssetRisk]
    stats: PCAStats
    warnings: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)


class PCARiskRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=100)
    weights: list[float] | None = Field(default=None, max_length=100)           # portfolio weights; default equal
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

    contributions: list[PortfolioVaRContribution]


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
    tickers: list[str]
    weights: list[float]
    lookback_period: str
    return_mode: ReturnMode                         # always "arith" — VaR is a P&L of a linear position
    horizon_days: int
    observations: int
    start_date_used: str
    end_date_used: str
    price_type: str                                 # "Adjusted Close" or "Close"
    portfolio_value: float | None = None
    stats: PortfolioVaREsStats
    points: list[PortfolioVaREsPoint]
    warnings: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)


class PortfolioVaREsRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=100)
    weights: list[float] | None = Field(default=None, max_length=100)           # portfolio weights; default equal
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    confidence_levels: list[float] = Field(default_factory=lambda: [0.95, 0.99], min_length=1, max_length=10)
    horizon_days: int = Field(default=1, ge=1, le=60)
    portfolio_value: float | None = Field(default=None, gt=0)


RegressionFrequency = Literal["daily", "weekly"]


class PortfolioRegressionRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=100)
    weights: list[float] = Field(min_length=1, max_length=100)
    benchmark: str = Field(default="URTH", min_length=1, max_length=32)
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    frequency: RegressionFrequency = "daily"
    base_currency: str = Field(default="EUR", min_length=3, max_length=3)


class RegressionStats(BaseModel):
    r_squared: float
    adj_r_squared: float
    correlation: float
    beta: float
    beta_std_err: float
    beta_t_stat: float
    alpha: float                      # per period, decimal
    alpha_annualized: float
    alpha_t_stat: float
    alpha_p_value: float
    total_volatility: float           # annualized portfolio volatility
    systematic_volatility: float      # annualized |beta| * benchmark volatility
    idiosyncratic_volatility: float   # annualized residual volatility
    benchmark_volatility: float
    tracking_error: float             # annualized std(portfolio - benchmark)
    information_ratio: float
    portfolio_return_annualized: float
    benchmark_return_annualized: float


class RegressionPoint(BaseModel):
    date: str
    benchmark_return: float
    portfolio_return: float


class RollingR2Point(BaseModel):
    date: str
    r_squared: float
    beta: float


class AssetRegression(BaseModel):
    ticker: str
    weight: float
    beta: float
    r_squared: float
    correlation: float
    beta_contribution: float          # weight * beta, sums to the portfolio beta


class PortfolioRegressionResponse(BaseModel):
    tickers: list[str]
    weights: list[float]
    benchmark: str
    frequency: RegressionFrequency
    lookback_period: str
    base_currency: str
    currencies: dict[str, str]        # quote currency of each series before conversion
    observations: int
    start_date_used: str
    end_date_used: str
    rolling_window: int
    stats: RegressionStats
    points: list[RegressionPoint]
    rolling: list[RollingR2Point]
    assets: list[AssetRegression]
    warnings: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)


class PortfolioHealthRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=100)
    weights: list[float] = Field(min_length=1, max_length=100)
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    risk_free_rate: float = Field(default=0.02, ge=0.0, le=0.5)


class CorrelationRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=100)
    weights: list[float] | None = Field(default=None, max_length=100)  # if provided, used for weighted avg correlation
    lookback_period: str = "3Y"
    auto_adjust: bool = True
    return_mode: ReturnMode = "log"


class YahooAllMetricsRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=200)
    asof: IsoDate | None = None
    period: str = "3Y"  # Default to 3 years
    auto_adjust: bool = True
    frequency: VolFrequency = "daily"
    confidence_levels: str = "0.95"
