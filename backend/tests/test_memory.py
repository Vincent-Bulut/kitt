"""Memory bounds: chunked Monte Carlo simulation, Monte Carlo request budget, memory-bounded caches."""

import tracemalloc

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.analytics import router
from backend.api.analytics.quant.simulation import simulate_gbm_paths
from backend.api.analytics.schemas import MONTE_CARLO_MAX_POINTS
from backend.api.cache import TTLStore, estimated_size


def naive_gbm_paths(mu, cov, weights, horizon, n_sims, seed, initial_value):
    """Reference: the original one-shot implementation (allocates n_sims x horizon x n_assets arrays)."""
    L = np.linalg.cholesky(cov + 1e-10 * np.eye(len(mu)))
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_sims, horizon, len(mu)))
    asset_paths = np.exp(np.cumsum(mu - 0.5 * np.diag(cov) + z @ L.T, axis=1))
    paths = np.concatenate([np.ones((n_sims, 1)), asset_paths @ weights], axis=1)
    return paths * initial_value


def _params(n_assets, seed=0):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n_assets, n_assets))
    return rng.normal(0, 1e-4, n_assets), (a @ a.T) * 1e-5, np.full(n_assets, 1 / n_assets)


@pytest.mark.parametrize("n_assets, horizon, n_sims", [(1, 10, 7), (3, 252, 1000), (12, 504, 1500)])
def test_chunked_simulation_matches_one_shot_reference(n_assets, horizon, n_sims):
    mu, cov, w = _params(n_assets)
    expected = naive_gbm_paths(mu, cov, w, horizon, n_sims, 42, 100.0)
    np.testing.assert_allclose(simulate_gbm_paths(mu, cov, w, horizon, n_sims, 42, 100.0), expected, rtol=1e-12)


def test_simulation_memory_does_not_scale_with_number_of_assets():
    # One-shot version: each (sims, horizon, assets) intermediate = 2000 * 2520 * 20 * 8 B = 806 MB
    mu, cov, w = _params(20)
    tracemalloc.start()
    paths = simulate_gbm_paths(mu, cov, w, 2520, 2000, 1, 1.0)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert paths.shape == (2000, 2521)
    assert peak < 200e6  # output (40 MB) + bounded chunks


def test_monte_carlo_request_over_budget_gives_422():
    client = TestClient(_app())
    body = {"tickers": ["SPY"], "weights": [1.0], "n_simulations": 20000, "horizon_days": 2520}
    assert 20000 * 2520 > MONTE_CARLO_MAX_POINTS
    resp = client.post("/analytics/yahoo/monte-carlo", json=body)
    assert resp.status_code == 422
    assert "n_simulations x horizon_days" in resp.text


def _app():
    app = FastAPI()
    app.include_router(router)
    return app


# --- memory-bounded cache -----------------------------------------------------

def test_memory_bounded_cache_evicts_to_stay_within_budget():
    store = TTLStore(ttl=60, max_mb=1)
    payload = list(np.random.default_rng(0).random(10_000))  # ~ 90 KB pickled -> ~450 KB estimated
    for i in range(10):
        store.set(i, payload)
    assert store.currsize <= 1_000_000
    assert 1 <= len(store) < 10
    assert store.get(9) is not None  # most recent kept


def test_value_larger_than_budget_is_served_but_not_cached():
    store = TTLStore(ttl=60, max_mb=0.1)
    big = list(range(100_000))
    assert estimated_size(big) > 100_000
    store.set("big", big)  # must not raise
    assert store.get("big") is None


def test_store_requires_exactly_one_bound():
    with pytest.raises(ValueError):
        TTLStore(ttl=60)
    with pytest.raises(ValueError):
        TTLStore(ttl=60, maxsize=10, max_mb=1)
