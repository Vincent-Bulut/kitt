"""HTTP tests for portfolio and transaction CRUD against an in-memory SQLite database."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import model
from backend.api.admin import router as admin_router
from backend.api.database import get_db
from backend.api.transactions import router as transactions_router


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    model.Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)

    with TestingSession() as db:
        db.add(model.Assets(symbol="CW8.PA", isin="FR0010315770", name="Amundi MSCI World", currency="EUR"))
        db.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(transactions_router)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


PORTFOLIO = {"name": "Core", "start_date": "2024-01-01", "manager_name": "Me"}


def test_portfolio_crud_roundtrip(client):
    created = client.post("/admin/portfolio", json=PORTFOLIO)
    assert created.status_code == 201
    pid = created.json()["id"]

    assert client.get(f"/admin/portfolio/{pid}").json()["name"] == "Core"

    updated = client.put(f"/admin/portfolio/{pid}", json={**PORTFOLIO, "description": "Long term"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "Long term"

    assert [p["id"] for p in client.get("/admin/portfolios").json()] == [pid]

    assert client.delete(f"/admin/portfolio/{pid}").status_code == 200
    assert client.get(f"/admin/portfolio/{pid}").status_code == 404


def test_portfolio_rejects_end_before_start(client):
    resp = client.post("/admin/portfolio", json={**PORTFOLIO, "end_date": "2023-01-01"})
    assert resp.status_code == 422


def test_duplicate_portfolio_name_returns_409_without_db_details(client):
    client.post("/admin/portfolio", json=PORTFOLIO)
    resp = client.post("/admin/portfolio", json=PORTFOLIO)
    assert resp.status_code == 409
    assert "UNIQUE" not in resp.text and "portfolio.name" not in resp.text  # no SQL leaked to the client


@pytest.mark.parametrize("method", ["get", "delete"])
def test_unknown_portfolio_returns_404(client, method):
    assert getattr(client, method)("/admin/portfolio/999").status_code == 404


def test_transaction_lifecycle(client):
    pid = client.post("/admin/portfolio", json=PORTFOLIO).json()["id"]
    payload = {"symbol": "CW8.PA", "date": "2024-02-01", "side": "BUY", "quantity": 3, "price": 450.0}

    created = client.post(f"/portfolios/{pid}/transactions", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["amount"] == pytest.approx(1350.0)
    assert body["currency"] == "EUR"  # inherited from the asset

    assert len(client.get(f"/portfolios/{pid}/transactions").json()) == 1
    assert client.delete(f"/transactions/{body['id']}").status_code == 200
    assert client.get(f"/transactions/{body['id']}").status_code == 404


def test_transaction_on_unknown_asset_returns_404(client):
    pid = client.post("/admin/portfolio", json=PORTFOLIO).json()["id"]
    payload = {"symbol": "NOPE", "date": "2024-02-01", "side": "BUY", "quantity": 1, "price": 1.0}
    assert client.post(f"/portfolios/{pid}/transactions", json=payload).status_code == 404


def test_transaction_rejects_non_positive_quantity(client):
    pid = client.post("/admin/portfolio", json=PORTFOLIO).json()["id"]
    payload = {"symbol": "CW8.PA", "date": "2024-02-01", "side": "SELL", "quantity": 0, "price": 1.0}
    assert client.post(f"/portfolios/{pid}/transactions", json=payload).status_code == 422
