"""Input validation of the analytics API: bad input must give 422, never 500.

All cases are rejected before any market data is fetched, so no network is needed.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from backend.api.analytics import router
from backend.api.analytics.schemas import IsoDate

app = FastAPI()
app.include_router(router)
client = TestClient(app)

DATES = "start_date=2024-01-01&end_date=2024-06-30"


@pytest.mark.parametrize("value", ["abc", "2025-13-45", "2025-02-30", "", "01/02/2024"])
def test_iso_date_rejects_invalid_dates(value):
    with pytest.raises(ValidationError):
        TypeAdapter(IsoDate).validate_python(value)


def test_iso_date_normalises_compact_format():
    assert TypeAdapter(IsoDate).validate_python("20240105") == "2024-01-05"


@pytest.mark.parametrize(
    "path",
    [
        "/analytics/yahoo/drawdowns?tickers=SPY&start_date=abc&end_date=2025-01-01",
        "/analytics/yahoo/var-es?tickers=SPY&start_date=2025-13-45&end_date=2025-12-31",
        "/analytics/yahoo/cumulative-returns?tickers=SPY&start_date=2024-01-01&end_date=2024-02-30",
        "/analytics/yahoo/perf?tickers=SPY&asof=yesterday",
        # invalid but chronologically "before" end_date: must be caught by the validator, not the range check
        "/analytics/yahoo/annualized-volatility?tickers=SPY&start_date=2024-02-30&end_date=2025-01-01",
    ],
)
def test_invalid_dates_in_query_give_422(path):
    assert client.get(path).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/analytics/yahoo/drawdowns?tickers=SPY&start_date=2025-01-01&end_date=2024-01-01",
        "/analytics/yahoo/annualized-volatility?tickers=SPY&start_date=2025-01-01&end_date=2024-01-01",
    ],
)
def test_reversed_date_range_in_query_gives_422(path):
    resp = client.get(path)
    assert resp.status_code == 422
    assert "start_date" in resp.json()["detail"]


def test_invalid_dates_in_body_give_422():
    body = {"tickers": ["SPY"], "start_date": "2024-02-30", "end_date": "2024-06-30"}
    assert client.post("/analytics/yahoo/drawdowns", json=body).status_code == 422


def test_reversed_date_range_in_body_gives_422():
    body = {"tickers": ["SPY"], "start_date": "2025-01-01", "end_date": "2024-01-01"}
    assert client.post("/analytics/yahoo/var-es", json=body).status_code == 422


@pytest.mark.parametrize(
    "path, limit",
    [
        ("/analytics/yahoo/perf?tickers={}", 500),
        ("/analytics/yahoo/drawdowns?tickers={}&" + DATES, 200),
        ("/analytics/yahoo/var-es?tickers={}&" + DATES, 200),
    ],
)
def test_too_many_tickers_in_query_gives_422(path, limit):
    tickers = ",".join(f"T{i}" for i in range(limit + 1))
    resp = client.get(path.format(tickers))
    assert resp.status_code == 422
    assert str(limit) in resp.json()["detail"]


def test_empty_ticker_list_gives_422():
    assert client.get("/analytics/yahoo/drawdowns?tickers=,,&" + DATES).status_code == 422


@pytest.mark.parametrize("levels", ["abc", "0.95,1.5", "0", ""])
def test_invalid_confidence_levels_give_422(levels):
    resp = client.get(f"/analytics/yahoo/var-es?tickers=SPY&{DATES}&confidence_levels={levels}")
    assert resp.status_code == 422


def test_oversized_optional_weights_give_422():
    body = {"tickers": ["SPY", "AGG"], "weights": [0.01] * 101}
    assert client.post("/analytics/yahoo/correlation", json=body).status_code == 422
