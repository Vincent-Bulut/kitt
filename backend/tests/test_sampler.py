"""Random portfolio sampler: history coverage, leveraged/inverse exclusion, diversification scoring.

Market data is synthetic (no network): download_close_daily_multi is replaced by a fake.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import model
from backend.api.analytics import router
from backend.api.analytics.quant.optimization import diversification_ratio
from backend.api.analytics.services import optimization as sampler_service
from backend.api.database import get_db

LONG = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
YOUNG = "NEW"      # listed ~4 months ago
INVERSE = "INV"    # mirror of AAA: a perfect hedge with a negative drift


def fake_prices(tickers, start_ts, end_ts, auto_adjust):
    dates = pd.bdate_range(start_ts, end_ts)
    rng = np.random.default_rng(0)
    rets = {t: rng.normal(0.0004 + 0.0001 * i, 0.01, len(dates)) for i, t in enumerate(LONG)}
    rets[YOUNG] = rng.normal(0.002, 0.01, len(dates))
    rets[INVERSE] = -2 * rets["AAA"] - 0.0002
    close = pd.DataFrame({t: 100 * np.exp(np.cumsum(rets[t])) for t in tickers if t in rets}, index=dates)
    if YOUNG in close:
        close.loc[close.index[:-85], YOUNG] = np.nan  # only ~4 months of history
    return close


@pytest.fixture(autouse=True)
def synthetic_market(monkeypatch):
    monkeypatch.setattr(sampler_service, "download_close_daily_multi", fake_prices)
    sampler_service.SAMPLER_CACHE.clear()


def run(**overrides):
    params = dict(
        tickers=[*LONG, YOUNG], portfolio_size=3, n_simulations=30, top_k=5, lookback_period="1Y",
        auto_adjust=True, risk_free_rate=0.02, diversification_weight=1.0, max_weight=1.0, min_weight=0.0,
        optimization="max_sharpe", seed=1,
    )
    return sampler_service.run_portfolio_sampler(**{**params, **overrides})


def test_young_asset_is_excluded_with_a_reason():
    out = run()
    assert YOUNG not in out["universe"]
    assert "History too short" in out["excluded"][YOUNG]
    assert all(YOUNG not in p["tickers"] for p in out["cloud"])


def test_every_portfolio_is_estimated_on_the_required_window():
    out = run()
    assert out["min_observations"] >= 0.8 * 250
    for p in out["top_by_composite"] + out["top_by_sharpe"]:
        assert p["observations"] >= out["min_observations"]


def test_lower_coverage_lets_young_assets_in():
    out = run(min_history_coverage=0.1)
    assert YOUNG in out["universe"]


def test_caller_exclusions_are_honoured_and_reported():
    out = run(tickers=[*LONG, INVERSE], excluded={INVERSE: "Leveraged or inverse product"})
    assert INVERSE not in out["universe"]
    assert out["excluded"][INVERSE] == "Leveraged or inverse product"


def test_composite_score_is_sharpe_plus_lambda_log_diversification_ratio():
    out = run(diversification_weight=0.5)
    for p in out["top_by_composite"]:
        assert p["diversification_ratio"] >= 1.0 - 1e-9  # long-only
        assert p["composite_score"] == pytest.approx(p["sharpe"] + 0.5 * np.log(p["diversification_ratio"]))


# --- diversification ratio ----------------------------------------------------

def test_diversification_ratio_reference_values():
    cov = np.diag([0.04, 0.04])
    assert diversification_ratio(np.array([1.0, 0.0]), cov) == pytest.approx(1.0)
    assert diversification_ratio(np.array([0.5, 0.5]), cov) == pytest.approx(np.sqrt(2))  # 2 uncorrelated assets
    perfectly_correlated = np.full((2, 2), 0.04)
    assert diversification_ratio(np.array([0.5, 0.5]), perfectly_correlated) == pytest.approx(1.0)


def test_diversification_ratio_depends_on_weights():
    cov = np.diag([0.04, 0.04, 0.04])
    concentrated = diversification_ratio(np.array([0.9, 0.05, 0.05]), cov)
    balanced = diversification_ratio(np.full(3, 1 / 3), cov)
    assert concentrated < balanced


# --- route: leveraged / inverse exclusion uses the referential names ----------

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    model.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        for t in LONG:
            db.add(model.Assets(symbol=t, isin=f"FR{t:0<10}", name=f"Fund {t} UCITS ETF", currency="EUR"))
        db.add(model.Assets(symbol=INVERSE, isin="FR000000INV", name="Amundi CAC 40 Daily (-2x) Inverse UCITS ETF Acc",
                            currency="EUR"))
        db.commit()

    def override_db():
        with Session() as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _post(client, **overrides):
    body = {"tickers": [*LONG, INVERSE], "portfolio_size": 3, "n_simulations": 30, "lookback_period": "1Y", **overrides}
    resp = client.post("/analytics/yahoo/portfolio-sampler", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_route_excludes_leveraged_and_inverse_by_default(client):
    out = _post(client)
    assert INVERSE not in out["universe"]
    assert out["excluded"][INVERSE] == "Leveraged or inverse product"


def test_route_can_keep_leveraged_products_on_request(client):
    out = _post(client, exclude_leveraged=False)
    assert INVERSE in out["universe"]
