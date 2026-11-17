"""Risk analytics: per-asset and portfolio VaR / ES, Monte Carlo simulation."""

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from backend.api import utils
from backend.api.analytics.market_data import PERIOD_DAYS, download_close_daily_multi
from backend.api.analytics.quant.returns import nearest_prev_price
from backend.api.analytics.quant.risk import as_return_series, es_summary, overlapping_horizon_returns, var_historical
from backend.api.analytics.quant.simulation import business_dates_forward, simulate_gbm_paths
from backend.api.analytics.schemas import ReturnMode
from backend.api.cache import TTLStore

RISK_CACHE = TTLStore(maxsize=2000, ttl=600)

MC_CACHE = TTLStore(maxsize=500, ttl=600)

PORTVAR_CACHE = TTLStore(maxsize=500, ttl=600)


def run_var_es(
    tickers: list[str],
    start_date: str,
    end_date: str,
    auto_adjust: bool,
    return_mode: ReturnMode,
    confidence_levels: list[float],
) -> dict[str, Any]:
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
    cached = RISK_CACHE.get(cache_key)
    if cached is not None:
        return cached

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    data: list[dict] = []
    errors: dict[str, str] = {}

    for t in tickers:
        try:
            if t not in close.columns:
                raise ValueError("Ticker not found in downloaded data")

            s = close[t].dropna()
            if s.empty:
                raise ValueError("No close prices for ticker in window")

            # find start/end used (nearest <= requested)
            _, start_used = nearest_prev_price(s, start_ts)
            if start_used is None:
                raise ValueError(f"No price data on or before {start_ts.date()}")

            _, end_used = nearest_prev_price(s, end_ts)
            if end_used is None:
                raise ValueError(f"No price data on or before {end_ts.date()}")

            window_prices = s.loc[start_used:end_used].dropna()
            if len(window_prices) < 10:
                raise ValueError("Not enough price points in window")

            if return_mode == "log":
                returns = np.log(window_prices).diff()
            else:
                returns = window_prices.pct_change()

            returns = as_return_series(returns)
            if len(returns) < 10:
                raise ValueError("Not enough returns to compute risk metrics")

            points = es_summary(returns, cls)

            data.append({
                "ticker": t,
                "start_date_requested": start_ts.date().isoformat(),
                "end_date_requested": end_ts.date().isoformat(),
                "start_date_used": start_used.date().isoformat(),
                "end_date_used": end_used.date().isoformat(),
                "observations": len(returns),
                "return_mode": return_mode,
                "horizon": "1D",
                "price_type": "Adjusted Close" if auto_adjust else "Close",
                "points": points,
            })

        except Exception as e:
            errors[t] = str(e)

    out = {"data": data, "errors": errors}
    RISK_CACHE.set(cache_key, out)
    return out


def run_monte_carlo(
    tickers: list[str],
    weights: list[float],
    horizon_days: int,
    n_simulations: int,
    lookback_period: str,
    auto_adjust: bool,
    seed: int,
    n_sample_paths: int,
    initial_value: float,
) -> dict[str, Any]:
    if len(tickers) != len(weights):
        raise ValueError("tickers and weights must have the same length")

    w_arr = np.array(weights, dtype=float)
    if np.any(w_arr < 0):
        raise ValueError("weights must be non-negative")
    w_sum = w_arr.sum()
    if w_sum <= 0:
        raise ValueError("sum of weights must be > 0")
    w_arr = w_arr / w_sum  # normalize

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
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
    cached = MC_CACHE.get(cache_key)
    if cached is not None:
        return cached

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    # Keep tickers that actually downloaded; drop weight components for missing tickers
    available = [t for t in tickers if t in close.columns]
    errors: dict[str, str] = {t: "Ticker not found in downloaded data"
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

    paths = simulate_gbm_paths(
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

    dates = business_dates_forward(end_ts, horizon_days)

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
    MC_CACHE.set(cache_key, out)
    return out


def run_portfolio_var_es(
    tickers: list[str],
    weights: list[float] | None,
    lookback_period: str,
    auto_adjust: bool,
    confidence_levels: list[float],
    horizon_days: int,
    portfolio_value: float | None,
) -> dict[str, Any]:
    if not tickers:
        raise ValueError("At least one ticker is required")

    horizon = int(horizon_days)
    if horizon < 1:
        raise ValueError("horizon_days must be >= 1")

    cls: list[float] = []
    for a in confidence_levels:
        if not (0.5 < float(a) < 1.0):
            raise ValueError("confidence_levels must be in (0.5, 1.0)")
        cls.append(float(a))
    if not cls:
        raise ValueError("At least one confidence level is required")
    cls = sorted(set(cls))

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

    days = PERIOD_DAYS.get(lookback_period.upper(), 1095)
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
    cached = PORTVAR_CACHE.get(cache_key)
    if cached is not None:
        return cached

    close = download_close_daily_multi(tickers, start_ts, end_ts, auto_adjust)
    if close.empty:
        raise ValueError("No price data returned by Yahoo")

    errors: dict[str, str] = {t: "Ticker not found in downloaded data"
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

    horizon_rets = overlapping_horizon_returns(daily, horizon)
    horizon_index = asset_rets.index[horizon - 1:]
    port = horizon_rets @ w                                  # exactly additive in the assets
    port_series = pd.Series(port, index=horizon_index)

    warnings: list[str] = []
    n_obs = len(port)
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

    points: list[dict[str, Any]] = []
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

        contributions: list[dict[str, Any]] = []
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
    PORTVAR_CACHE.set(cache_key, out)
    return out
