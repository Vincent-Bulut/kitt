"""Monte Carlo simulation of price paths (geometric Brownian motion)."""

import numpy as np
import pandas as pd


def business_dates_forward(start: pd.Timestamp, n_steps: int) -> list[str]:
    """Returns n_steps+1 business-day dates starting from `start` inclusive."""
    idx = pd.bdate_range(start=start, periods=n_steps + 1)
    return [d.date().isoformat() for d in idx]


# Max number of floats per per-asset intermediate array (~32 MB)
_CHUNK_ELEMENTS = 4_000_000


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

    # Only the portfolio paths are kept: (n_sims, horizon + 1), first column = initial value.
    portfolio_paths = np.empty((n_sims, horizon + 1))
    portfolio_paths[:, 0] = 1.0

    # Per-asset intermediates are (sims, horizon, n_assets): building them for all simulations at
    # once needs n_sims * horizon * n_assets * 8 bytes per array (40 GB for 20,000 x 2,520 x 100).
    # Process simulations in chunks instead. Drawing the normals chunk by chunk consumes the same
    # random stream in the same order, so results are identical to a one-shot simulation.
    chunk = max(1, _CHUNK_ELEMENTS // max(1, horizon * n_assets))
    for start in range(0, n_sims, chunk):
        stop = min(start + chunk, n_sims)
        z = rng.standard_normal((stop - start, horizon, n_assets))
        log_rets = z @ L.T  # correlated shocks
        log_rets += drift
        np.cumsum(log_rets, axis=1, out=log_rets)  # cumulative log-returns
        np.exp(log_rets, out=log_rets)  # asset prices, normalised to 1 at t=0
        portfolio_paths[start:stop, 1:] = log_rets @ weights

    return portfolio_paths * float(initial_value)
