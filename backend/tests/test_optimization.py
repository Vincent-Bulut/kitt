"""Mean-variance portfolio construction."""

import numpy as np
import pytest

from backend.api.analytics import _max_sharpe_portfolio, _min_variance_portfolio, _portfolio_perf


def test_portfolio_perf_two_uncorrelated_assets():
    mu = np.array([0.05, 0.10])
    cov = np.diag([0.04, 0.09])
    ret, vol = _portfolio_perf(np.array([0.5, 0.5]), mu, cov)
    assert ret == pytest.approx(0.075)
    assert vol == pytest.approx(np.sqrt(0.25 * 0.04 + 0.25 * 0.09))


def test_min_variance_matches_closed_form_for_uncorrelated_assets():
    # Without correlation, w_i is proportional to 1 / sigma_i^2
    variances = np.array([0.04, 0.09, 0.16])
    cov = np.diag(variances)
    w = _min_variance_portfolio(np.zeros(3), cov)

    expected = (1 / variances) / (1 / variances).sum()
    np.testing.assert_allclose(w, expected, atol=1e-4)


def test_max_sharpe_weights_are_long_only_and_fully_invested():
    mu = np.array([0.04, 0.08, 0.12])
    cov = np.array(
        [
            [0.010, 0.002, 0.001],
            [0.002, 0.040, 0.006],
            [0.001, 0.006, 0.090],
        ]
    )
    w = _max_sharpe_portfolio(mu, cov, rf=0.02)

    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    assert (w >= -1e-9).all()

    def sharpe(weights):
        ret, vol = _portfolio_perf(weights, mu, cov)
        return (ret - 0.02) / vol

    assert sharpe(w) >= sharpe(np.full(3, 1 / 3))
