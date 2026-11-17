"""Ordinary least squares regression against a benchmark."""

import numpy as np

REGRESSION_ANNUALIZATION = {"daily": 252.0, "weekly": 52.0}
REGRESSION_ROLLING_WINDOW = {"daily": 63, "weekly": 26}  # ~ one quarter / half a year


def ols_simple(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """OLS of y = alpha + beta * x + e, with classical standard errors."""
    n = len(x)
    x_mean, y_mean = float(np.mean(x)), float(np.mean(y))
    sxx = float(np.sum((x - x_mean) ** 2))
    syy = float(np.sum((y - y_mean) ** 2))
    if sxx <= 0:
        raise ValueError("Benchmark returns have zero variance")

    beta = float(np.sum((x - x_mean) * (y - y_mean)) / sxx)
    alpha = y_mean - beta * x_mean
    resid = y - alpha - beta * x
    sse = float(np.sum(resid ** 2))

    r2 = 1.0 - sse / syy if syy > 0 else 0.0
    dof = n - 2
    sigma2 = sse / dof if dof > 0 else 0.0
    se_beta = float(np.sqrt(sigma2 / sxx))
    se_alpha = float(np.sqrt(sigma2 * (1.0 / n + x_mean ** 2 / sxx)))

    return {
        "alpha": alpha,
        "beta": beta,
        "r_squared": r2,
        "adj_r_squared": 1.0 - (1.0 - r2) * (n - 1) / dof if dof > 0 else r2,
        "se_alpha": se_alpha,
        "se_beta": se_beta,
        "resid_std": float(np.sqrt(sigma2)),
        "dof": dof,
    }
