"""Value-at-Risk and Expected Shortfall estimators."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from backend.api.analytics.quant.risk import (
    es_cf_empirical_tail,
    es_gaussian,
    es_historical,
    var_cornish_fisher,
    var_gaussian,
    var_historical,
)


@pytest.fixture
def normal_returns() -> pd.Series:
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(loc=0.0005, scale=0.01, size=50_000))


def test_historical_var_on_known_distribution():
    # Returns -1%, -2%, ..., -100% shuffled: the 5% left quantile is about -95%.
    returns = pd.Series(-np.arange(1, 101) / 100.0)
    assert var_historical(returns, 0.95) == pytest.approx(0.9505, abs=1e-4)


def test_historical_es_is_mean_of_the_tail():
    returns = pd.Series([-0.10, -0.05, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07])
    var = var_historical(returns, 0.9)
    es = es_historical(returns, 0.9)
    tail = returns[returns <= -var]
    assert es == pytest.approx(-tail.mean())
    assert es >= var


def test_gaussian_var_matches_closed_form():
    returns = pd.Series([0.01, -0.02, 0.015, -0.005, 0.0, 0.02, -0.01])
    mu, sigma = returns.mean(), returns.std(ddof=1)
    expected = -(mu + sigma * norm.ppf(0.01))
    assert var_gaussian(returns, 0.99) == pytest.approx(expected)


def test_gaussian_es_exceeds_var(normal_returns):
    for alpha in (0.95, 0.99):
        assert es_gaussian(normal_returns, alpha) > var_gaussian(normal_returns, alpha)


def test_historical_converges_to_gaussian_on_normal_data(normal_returns):
    assert var_historical(normal_returns, 0.99) == pytest.approx(var_gaussian(normal_returns, 0.99), rel=0.03)
    assert es_historical(normal_returns, 0.99) == pytest.approx(es_gaussian(normal_returns, 0.99), rel=0.03)


def test_cornish_fisher_reduces_to_gaussian_without_skew_or_kurtosis(normal_returns):
    assert var_cornish_fisher(normal_returns, 0.99) == pytest.approx(var_gaussian(normal_returns, 0.99), rel=0.02)


def test_cornish_fisher_widens_var_for_fat_left_tail():
    rng = np.random.default_rng(0)
    base = rng.normal(0.0, 0.01, size=5_000)
    crashes = rng.normal(-0.08, 0.02, size=50)
    returns = pd.Series(np.concatenate([base, crashes]))
    assert var_cornish_fisher(returns, 0.99) > var_gaussian(returns, 0.99)
    assert es_cf_empirical_tail(returns, 0.99) >= var_cornish_fisher(returns, 0.99)


@pytest.mark.parametrize(
    "estimator", [var_historical, es_historical, var_gaussian, es_gaussian, var_cornish_fisher, es_cf_empirical_tail]
)
def test_estimators_ignore_invalid_values_and_handle_empty_input(estimator):
    assert estimator(pd.Series([], dtype=float), 0.95) == 0.0
    assert estimator(pd.Series([np.nan, np.inf, -np.inf]), 0.95) == 0.0


def test_zero_volatility_gives_zero_parametric_var():
    flat = pd.Series([0.0] * 20)
    assert var_gaussian(flat, 0.99) == 0.0
    assert es_gaussian(flat, 0.99) == 0.0
    assert var_cornish_fisher(flat, 0.99) == 0.0
