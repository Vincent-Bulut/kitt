"""Portfolio diagnostics: correlation, health ratios, PCA risk decomposition and benchmark regression."""

from typing import Any

import numpy as np
import pandas as pd
from cachetools import TTLCache
from scipy.stats import t as student_t

from backend.api.analytics.market_data import PERIOD_DAYS, convert_close_to_base, download_close_daily_multi
from backend.api.analytics.quant.pca import pc_interpretation, pc_sign_normalized
from backend.api.analytics.quant.regression import REGRESSION_ANNUALIZATION, REGRESSION_ROLLING_WINDOW, ols_simple
from backend.api.analytics.schemas import PCAMatrixType, ReturnMode

CORR_CACHE = TTLCache(maxsize=500, ttl=600)

HEALTH_CACHE = TTLCache(maxsize=500, ttl=600)

PCA_CACHE = TTLCache(maxsize=200, ttl=600)

REGRESSION_CACHE = TTLCache(maxsize=500, ttl=600)


def run_correlation(
    tickers: list[str],
    weights: list[float] | None,
    lookback_period: str,
    auto_adjust: bool,
    return_mode: ReturnMode,
) -> dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required to compute a correlation matrix")

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    norm_weights: np.ndarray | None = None
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

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: dict[str, str] = {t: "Ticker not found in downloaded data"
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

    weighted_avg: float | None = None
    if norm_weights is not None and norm_weights.size == n:
        # Weighted off-diagonal mean: sum_{i<j} 2*w_i*w_j*rho_ij / sum_{i<j} 2*w_i*w_j
        ww = np.outer(norm_weights, norm_weights)
        num = float(np.nansum(ww[iu] * off_diag))
        den = float(np.nansum(ww[iu]))
        weighted_avg = float(num / den) if den > 0 else None

    min_pair_obj: dict[str, Any] | None = None
    max_pair_obj: dict[str, Any] | None = None
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
        "observations": len(rets),
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


def run_portfolio_health(
    tickers: list[str],
    weights: list[float],
    lookback_period: str,
    auto_adjust: bool,
    risk_free_rate: float,
) -> dict[str, Any]:
    if len(tickers) != len(weights):
        raise ValueError("tickers and weights must have the same length")

    w_arr = np.array(weights, dtype=float)
    if np.any(w_arr < 0):
        raise ValueError("weights must be non-negative")
    w_sum = w_arr.sum()
    if w_sum <= 0:
        raise ValueError("sum of weights must be > 0")
    w_arr = w_arr / w_sum

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
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

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: dict[str, str] = {t: "Ticker not found in downloaded data"
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
        "observations": len(port_rets),
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


def run_pca_risk(
    tickers: list[str],
    weights: list[float] | None,
    lookback_period: str,
    auto_adjust: bool,
    return_mode: ReturnMode,
    matrix_type: PCAMatrixType,
    n_components: int,
    top_loadings: int,
) -> dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required to run a PCA risk decomposition")

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    w_in: np.ndarray | None = None
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

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: dict[str, str] = {t: "Ticker not found in downloaded data"
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
    warnings: list[str] = []
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
    components: list[dict[str, Any]] = []
    normalized_vecs: list[np.ndarray] = []
    for i in range(n):
        vec = pc_sign_normalized(eigvecs[:, i].copy())
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
            "interpretation": pc_interpretation(
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

    assets: list[dict[str, Any]] = []
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
        "observations": len(rets),
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


def run_portfolio_regression(
    tickers: list[str],
    weights: list[float],
    benchmark: str,
    lookback_period: str,
    auto_adjust: bool,
    frequency: str,
    base_currency: str,
) -> dict[str, Any]:
    if len(tickers) != len(weights):
        raise ValueError("tickers and weights must have the same length")

    benchmark = benchmark.strip().upper()
    if not benchmark:
        raise ValueError("benchmark is required")
    base_currency = base_currency.strip().upper()

    w_arr = np.array(weights, dtype=float)
    if np.any(w_arr < 0):
        raise ValueError("weights must be non-negative")
    if w_arr.sum() <= 0:
        raise ValueError("sum of weights must be > 0")
    w_arr = w_arr / w_arr.sum()

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    cache_key = (
        "regression",
        tuple(tickers),
        tuple(round(float(x), 6) for x in w_arr.tolist()),
        benchmark,
        lookback_period,
        auto_adjust,
        frequency,
        base_currency,
        end_ts.date().isoformat(),
    )
    if cache_key in REGRESSION_CACHE:
        return REGRESSION_CACHE[cache_key]

    download = list(dict.fromkeys([*tickers, benchmark]))
    close = download_close_daily_multi(download, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")
    if benchmark not in close.columns or close[benchmark].dropna().empty:
        raise ValueError(f"Benchmark '{benchmark}' not found on Yahoo Finance")

    available = [t for t in tickers if t in close.columns and not close[t].dropna().empty]
    errors: dict[str, str] = {t: "Ticker not found in downloaded data" for t in tickers if t not in available}
    if not available:
        raise ValueError("No tickers available in downloaded data")

    keep_mask = np.array([t in available for t in tickers])
    w_kept = w_arr[keep_mask]
    w_kept = w_kept / w_kept.sum()

    # Same currency on both sides, otherwise FX moves end up in the residual and depress R²
    prices, currencies, warnings = convert_close_to_base(
        close[list(dict.fromkeys([*available, benchmark]))], base_currency, start_ts, end_ts
    )
    prices = prices.dropna(how="any")
    if frequency == "weekly":
        prices = prices.resample("W-FRI").last().dropna(how="any")
    rets = prices.pct_change().dropna().loc[start_ts:]

    window = REGRESSION_ROLLING_WINDOW[frequency]
    if len(rets) < 20:
        raise ValueError("Not enough overlapping return observations (need >= 20)")

    asset_rets = rets[available]
    port = pd.Series(asset_rets.to_numpy() @ w_kept, index=rets.index)  # fixed weights, rebalanced each period
    bench = rets[benchmark]

    x, y = bench.to_numpy(), port.to_numpy()
    fit = ols_simple(x, y)
    ann = REGRESSION_ANNUALIZATION[frequency]
    sqrt_ann = float(np.sqrt(ann))

    beta_t = fit["beta"] / fit["se_beta"] if fit["se_beta"] > 0 else 0.0
    alpha_t = fit["alpha"] / fit["se_alpha"] if fit["se_alpha"] > 0 else 0.0
    alpha_p = float(2.0 * student_t.sf(abs(alpha_t), fit["dof"])) if fit["dof"] > 0 else 1.0

    active = y - x
    te = float(np.std(active, ddof=1)) * sqrt_ann
    bench_vol = float(np.std(x, ddof=1)) * sqrt_ann

    # Rolling fit: R² is the squared rolling correlation, beta = cov / var
    roll_corr = port.rolling(window).corr(bench)
    roll_beta = port.rolling(window).cov(bench) / bench.rolling(window).var()
    rolling = [
        {"date": d.date().isoformat(), "r_squared": float(c ** 2), "beta": float(b)}
        for d, c, b in zip(rets.index, roll_corr, roll_beta)
        if np.isfinite(c) and np.isfinite(b)
    ]

    assets = []
    for ticker, w in zip(available, w_kept):
        a_fit = ols_simple(x, asset_rets[ticker].to_numpy())
        assets.append({
            "ticker": ticker,
            "weight": float(w),
            "beta": a_fit["beta"],
            "r_squared": a_fit["r_squared"],
            "correlation": float(np.sign(a_fit["beta"]) * np.sqrt(max(a_fit["r_squared"], 0.0))),
            "beta_contribution": float(w * a_fit["beta"]),
        })

    out = {
        "tickers": available,
        "weights": w_kept.tolist(),
        "benchmark": benchmark,
        "frequency": frequency,
        "lookback_period": lookback_period,
        "base_currency": base_currency,
        "currencies": currencies,
        "observations": len(rets),
        "start_date_used": rets.index[0].date().isoformat(),
        "end_date_used": rets.index[-1].date().isoformat(),
        "rolling_window": window,
        "stats": {
            "r_squared": fit["r_squared"],
            "adj_r_squared": fit["adj_r_squared"],
            "correlation": float(np.sign(fit["beta"]) * np.sqrt(max(fit["r_squared"], 0.0))),
            "beta": fit["beta"],
            "beta_std_err": fit["se_beta"],
            "beta_t_stat": beta_t,
            "alpha": fit["alpha"],
            "alpha_annualized": fit["alpha"] * ann,
            "alpha_t_stat": alpha_t,
            "alpha_p_value": alpha_p,
            "total_volatility": float(np.std(y, ddof=1)) * sqrt_ann,
            "systematic_volatility": abs(fit["beta"]) * bench_vol,
            "idiosyncratic_volatility": fit["resid_std"] * sqrt_ann,
            "benchmark_volatility": bench_vol,
            "tracking_error": te,
            "information_ratio": float(np.mean(active)) * ann / te if te > 0 else 0.0,
            "portfolio_return_annualized": float(np.mean(y)) * ann,
            "benchmark_return_annualized": float(np.mean(x)) * ann,
        },
        "points": [
            {"date": d.date().isoformat(), "benchmark_return": float(bx), "portfolio_return": float(py)}
            for d, bx, py in zip(rets.index, x, y)
        ],
        "rolling": rolling,
        "assets": assets,
        "warnings": warnings,
        "errors": errors,
    }
    REGRESSION_CACHE[cache_key] = out
    return out
