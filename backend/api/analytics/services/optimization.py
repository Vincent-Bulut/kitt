"""Portfolio construction: efficient frontier, Black-Litterman and random portfolio sampler."""

from typing import Any

import numpy as np
import pandas as pd

from backend.api.analytics.market_data import PERIOD_DAYS, download_close_daily_multi
from backend.api.analytics.quant.optimization import (
    avg_off_diag_correlation,
    black_litterman_posterior,
    build_portfolio_descriptor,
    max_sharpe_portfolio,
    min_variance_for_target,
    min_variance_portfolio,
    optimize_subset,
    optimize_with_bounds,
    portfolio_perf,
)
from backend.api.cache import TTLStore

EF_CACHE = TTLStore(ttl=600, max_mb=16)

SAMPLER_CACHE = TTLStore(ttl=600, max_mb=16)

BL_CACHE = TTLStore(ttl=600, max_mb=8)


def run_efficient_frontier(
    tickers: list[str],
    weights: list[float] | None,
    lookback_period: str,
    auto_adjust: bool,
    risk_free_rate: float,
    n_points: int,
) -> dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required to compute an efficient frontier")

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    current_w_arr: np.ndarray | None = None
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
    cached = EF_CACHE.get(cache_key)
    if cached is not None:
        return cached

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: dict[str, str] = {t: "Ticker not found in downloaded data"
                              for t in tickers if t not in close.columns}
    if len(available) < 2:
        raise ValueError("Need at least 2 tickers with price data for the frontier")

    # Re-align current weights to available tickers (renormalize) if provided
    current_w_aligned: np.ndarray | None = None
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
    w_minvar = min_variance_portfolio(mu, cov)
    w_tangent = max_sharpe_portfolio(mu, cov, rf)

    minvar_desc = build_portfolio_descriptor(w_minvar, available, mu, cov, rf)
    tangent_desc = build_portfolio_descriptor(w_tangent, available, mu, cov, rf)

    # Frontier: span from min-var return up to max individual asset return
    r_min = minvar_desc["expected_return"]
    r_max = float(np.max(mu))
    if r_max <= r_min:
        # Edge case: nothing to span — just emit the single point
        targets = np.array([r_min])
    else:
        targets = np.linspace(r_min, r_max, int(n_points))

    frontier_points: list[dict[str, float]] = []
    for t in targets:
        w_opt = min_variance_for_target(float(t), mu, cov)
        if w_opt is None:
            continue
        ret, vol = portfolio_perf(w_opt, mu, cov)
        sharpe = ((ret - rf) / vol) if vol > 0 else 0.0
        frontier_points.append({
            "expected_return": ret,
            "volatility": vol,
            "sharpe": sharpe,
        })

    # Individual assets
    asset_points: list[dict[str, Any]] = []
    for i, t in enumerate(available):
        sigma_i = float(np.sqrt(max(cov[i, i], 0.0)))
        asset_points.append({
            "ticker": t,
            "expected_return": float(mu[i]),
            "volatility": sigma_i,
        })

    current_desc: dict[str, Any] | None = None
    if current_w_aligned is not None and current_w_aligned.size == len(available):
        current_desc = build_portfolio_descriptor(current_w_aligned, available, mu, cov, rf)

    out = {
        "tickers": available,
        "risk_free_rate": rf,
        "observations": len(log_rets),
        "start_date_used": log_rets.index[0].date().isoformat(),
        "end_date_used": log_rets.index[-1].date().isoformat(),
        "frontier": frontier_points,
        "assets": asset_points,
        "min_variance": minvar_desc,
        "max_sharpe": tangent_desc,
        "current_portfolio": current_desc,
        "errors": errors,
    }
    EF_CACHE.set(cache_key, out)
    return out


def run_black_litterman(
    tickers: list[str],
    prior_weights: list[float] | None,
    views: list[Any],
    lookback_period: str,
    auto_adjust: bool,
    risk_free_rate: float,
    risk_aversion: float,
    tau: float,
    max_weight: float,
    min_weight: float,
) -> dict[str, Any]:
    if len(tickers) < 2:
        raise ValueError("At least 2 tickers are required for the Black-Litterman model")

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
    end_ts = pd.Timestamp.now().normalize()
    start_ts = end_ts - pd.Timedelta(days=days)

    # Normalize prior (market) weights aligned to the input ticker order.
    prior_arr: np.ndarray | None = None
    if prior_weights is not None:
        if len(prior_weights) != len(tickers):
            raise ValueError("prior_weights length must match tickers length")
        pw = np.array(prior_weights, dtype=float)
        if np.any(pw < 0):
            raise ValueError("prior_weights must be non-negative")
        s = pw.sum()
        if s > 0:
            prior_arr = pw / s

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in tickers if t in close.columns]
    errors: dict[str, str] = {t: "Ticker not found in downloaded data"
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
    rows: list[np.ndarray] = []
    q_vals: list[float] = []
    conf_vals: list[float] = []
    warnings: list[str] = []
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
        q_vals.append(float(v.value))
        conf_vals.append(float(getattr(v, "confidence", 0.5)))

    if rows:
        P = np.vstack(rows)
        Q = np.array(q_vals, dtype=float)
        confidences = np.array(conf_vals, dtype=float)
    else:
        P = None
        Q = None
        confidences = None

    implied, posterior = black_litterman_posterior(
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

    w_opt = optimize_with_bounds(neg_sharpe, n, max_weight, min_weight)
    if w_opt is None:
        warnings.append("Max-Sharpe optimization did not converge; using equal weights")
        w_opt = np.full(n, 1.0 / n)

    w_minvar = optimize_with_bounds(lambda w: float(w @ cov @ w), n, max_weight, min_weight)
    if w_minvar is None:
        w_minvar = np.full(n, 1.0 / n)

    optimal_desc = build_portfolio_descriptor(w_opt, available, posterior, cov, rf)
    minvar_desc = build_portfolio_descriptor(w_minvar, available, posterior, cov, rf)

    asset_points: list[dict[str, Any]] = []
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
        "observations": len(log_rets),
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


def run_portfolio_sampler(
    tickers: list[str],
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
) -> dict[str, Any]:
    # de-dup tickers while preserving order
    seen: set = set()
    uniq_tickers: list[str] = []
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            uniq_tickers.append(t)

    if len(uniq_tickers) < portfolio_size:
        raise ValueError(
            f"Need at least {portfolio_size} unique tickers in the universe (got {len(uniq_tickers)})"
        )

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
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
    cached = SAMPLER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    close = download_close_daily_multi(uniq_tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    available = [t for t in uniq_tickers if t in close.columns]
    errors: dict[str, str] = {
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
    cloud: list[dict[str, float]] = []
    portfolios: list[dict[str, Any]] = []
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

        w = optimize_subset(mu_sub, cov_sub, float(risk_free_rate), optimization, float(max_weight), float(min_weight))
        if w is None:
            n_failed += 1
            continue

        ret = float(np.dot(w, mu_sub))
        var = float(w @ cov_sub @ w)
        vol = float(np.sqrt(max(var, 0.0)))
        sharpe = ((ret - float(risk_free_rate)) / vol) if vol > 0 else 0.0

        corr_mat = sub_rets.corr().to_numpy()
        avg_corr = avg_off_diag_correlation(corr_mat)

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
        "n_simulations_evaluated": len(portfolios),
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
    SAMPLER_CACHE.set(cache_key, out)
    return out
