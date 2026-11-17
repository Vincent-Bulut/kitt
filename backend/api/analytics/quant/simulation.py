"""Monte Carlo simulation of price paths (geometric Brownian motion)."""

import numpy as np
import pandas as pd


def business_dates_forward(start: pd.Timestamp, n_steps: int) -> list[str]:
    """Returns n_steps+1 business-day dates starting from `start` inclusive."""
    idx = pd.bdate_range(start=start, periods=n_steps + 1)
    return [d.date().isoformat() for d in idx]


def simulate_gbm_paths(
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
