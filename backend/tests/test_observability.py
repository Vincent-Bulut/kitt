"""Error handling, request ids and upload limits."""

import io
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import observability
from backend.api.database import get_db
from backend.api.referential import MAX_UPLOAD_BYTES
from backend.api.referential import router as referential_router


@pytest.fixture
def client():
    app = FastAPI()
    observability.install(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail: password=hunter2")

    @app.get("/ok")
    def ok():
        return {"ok": True}

    app.include_router(referential_router)
    app.dependency_overrides[get_db] = lambda: None  # uploads below are rejected before any DB access
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_returns_generic_500_and_logs_details(client, caplog):
    with caplog.at_level(logging.ERROR, logger="backend.api"):
        resp = client.get("/boom", headers={"X-Request-ID": "req-123"})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error", "request_id": "req-123"}
    assert "hunter2" not in resp.text
    assert resp.headers["X-Request-ID"] == "req-123"

    record = next(r for r in caplog.records if "unhandled error" in r.getMessage())
    assert record.exc_info is not None and "hunter2" in str(record.exc_info[1])


def test_request_id_is_generated_and_returned(client):
    resp = client.get("/ok")
    assert resp.status_code == 200
    assert len(resp.headers["X-Request-ID"]) == 12


def test_request_is_logged_with_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO, logger="backend.api"):
        client.get("/ok")
    assert any('path="/ok" status=200 duration_ms=' in r.getMessage() for r in caplog.records)


def _upload(client, content: bytes, name: str = "assets.xlsx"):
    files = {"file": (name, io.BytesIO(content), "application/octet-stream")}
    return client.post("/referential/upload-excel", files=files)


def test_oversized_upload_is_rejected_with_413(client):
    assert _upload(client, b"x" * (MAX_UPLOAD_BYTES + 1)).status_code == 413


def test_empty_upload_gives_clean_400(client):
    resp = _upload(client, b"")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Empty file."


def test_malformed_excel_gives_generic_400(client):
    resp = _upload(client, b"definitely not an xlsx file")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or unreadable Excel file."


def test_yfinance_errors_are_logged_as_warnings_but_app_errors_stay_errors(capsys):
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        observability.configure_logging()
        logging.getLogger("yfinance").error("$FOO.PA: possibly delisted; no timezone found")
        logging.getLogger("backend.api").error("real application failure")
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    lines = capsys.readouterr().err.splitlines()
    yf_line = next(line for line in lines if "possibly delisted" in line)
    app_line = next(line for line in lines if "real application failure" in line)
    assert "level=WARNING logger=yfinance" in yf_line
    assert "level=ERROR logger=backend.api" in app_line
