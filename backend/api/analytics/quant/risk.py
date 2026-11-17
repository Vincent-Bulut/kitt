"""Value-at-Risk and Expected Shortfall estimators (pure functions).

All estimators take a return series and a confidence level alpha (e.g. 0.99)
and return the loss as a positive number."""

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm


def as_return_series(returns: pd.Series) -> pd.Series:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    return r

def var_historical(returns: pd.Series, alpha: float) -> float:
    r = as_return_series(returns).to_numpy()
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1 - alpha)   # left tail threshold in return space
    return float(-q)                # loss positive

def es_historical(returns: pd.Series, alpha: float) -> float:
    r = as_return_series(returns).to_numpy()
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1 - alpha)
    tail = r[r <= q]
    return float(-np.mean(tail)) if tail.size else 0.0

def var_gaussian(returns: pd.Series, alpha: float) -> float:
    r = as_return_series(returns)
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
    r = as_return_series(returns)
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
    r = as_return_series(returns)
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
    r = as_return_series(returns).to_numpy()
    if r.size == 0:
        return 0.0

    var_cf_loss = var_cornish_fisher(pd.Series(r), alpha)  # positive loss
    threshold_return = -var_cf_loss                         # return threshold (negative)

    tail = r[r <= threshold_return]
    return float(-np.mean(tail)) if tail.size else 0.0

def es_summary(returns: pd.Series, confidence_levels: list[float]) -> list[dict[str, Any]]:
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


def overlapping_horizon_returns(rets: np.ndarray, horizon: int) -> np.ndarray:
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
