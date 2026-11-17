"""Logging, request tracing and last-resort error handling.

- Logs are single-line key=value records (logfmt), easy to grep and to ingest.
- Every request gets an id (X-Request-ID, taken from the client if provided)
  that is logged with the request and returned in error responses.
- Unhandled exceptions are logged with their traceback; the client only gets
  a generic message and the request id, never internal details.
"""

import logging
import os
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

log = logging.getLogger("backend.api")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "ts=%(asctime)s level=%(levelname)s logger=%(name)s request_id=%(request_id)s msg=%(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id  # still readable by the exception handler below
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            log.info(
                'method=%s path="%s" status=%s duration_ms=%.0f',
                request.method, request.url.path, status, duration_ms,
            )
            request_id_var.reset(token)

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        # Runs outside the middleware (ServerErrorMiddleware), after the context var was reset
        request_id = getattr(request.state, "request_id", "-")
        token = request_id_var.set(request_id)
        try:
            log.error('unhandled error on %s "%s"', request.method, request.url.path, exc_info=exc)
        finally:
            request_id_var.reset(token)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
