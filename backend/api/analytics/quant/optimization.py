"""Mean-variance and Black-Litterman portfolio construction (pure functions)."""

from typing import Any

import numpy as np
from scipy.optimize import minimize


def portfolio_perf(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> tuple[float, float]:
    """Return (expected_return, volatility), both annualized."""
    ret = float(np.dot(weights, mu))
    var = float(weights @ cov @ weights)
    vol = float(np.sqrt(max(var, 0.0)))
    return ret, vol


def min_variance_for_target(
    target_return: float,
    mu: np.ndarray,
    cov: np.ndarray,
) -> np.ndarray | None:
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


def min_variance_portfolio(mu: np.ndarray, cov: np.ndarray) -> np.ndarray:
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


def max_sharpe_portfolio(mu: np.ndarray, cov: np.ndarray, rf: float) -> np.ndarray:
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


def build_portfolio_descriptor(
    w: np.ndarray,
    tickers: list[str],
    mu: np.ndarray,
    cov: np.ndarray,
    rf: float,
) -> dict[str, Any]:
    ret, vol = portfolio_perf(w, mu, cov)
    sharpe = ((ret - rf) / vol) if vol > 0 else 0.0
    return {
        "weights": {tickers[i]: float(w[i]) for i in range(len(tickers))},
        "expected_return": ret,
        "volatility": vol,
        "sharpe": sharpe,
    }


def optimize_with_bounds(
    objective,
    n: int,
    max_weight: float = 1.0,
    min_weight: float = 0.0,
) -> np.ndarray | None:
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


def black_litterman_posterior(
    cov: np.ndarray,
    w_mkt: np.ndarray,
    rf: float,
    risk_aversion: float,
    tau: float,
    P: np.ndarray | None,
    Q: np.ndarray | None,
    confidences: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
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


def diversification_ratio(weights: np.ndarray, cov: np.ndarray) -> float:
    """sum(w_i * sigma_i) / sigma_p (Choueifaty & Coignard).

    1 for a single asset or perfectly correlated assets, higher the more the weighted assets offset
    each other. Uses the actual weights, unlike an average of pairwise correlations.
    """
    w = np.asarray(weights, dtype=float)
    sigma = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    port_vol = float(np.sqrt(max(float(w @ cov @ w), 0.0)))
    if port_vol <= 0:
        return 1.0
    return float(w @ sigma) / port_vol


def avg_off_diag_correlation(corr_mat: np.ndarray) -> float:
    n = corr_mat.shape[0]
    if n < 2:
        return 0.0
    iu = np.triu_indices(n, k=1)
    vals = corr_mat[iu]
    return float(np.nanmean(vals)) if vals.size else 0.0


def optimize_subset(
    mu_sub: np.ndarray,
    cov_sub: np.ndarray,
    rf: float,
    mode: str,
    max_weight: float = 1.0,
    min_weight: float = 0.0,
) -> np.ndarray | None:
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
