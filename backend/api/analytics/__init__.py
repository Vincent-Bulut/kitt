"""Quantitative analytics API (performance, risk, portfolio construction).

Layers:
    market_data  network I/O (Yahoo Finance prices and FX)
    quant/       pure computations, unit-tested without network
    services/    orchestration: data download + computation + caching
    routes/      thin FastAPI routers
"""

from fastapi import APIRouter

from backend.api.analytics.routes import performance, portfolio, risk

router = APIRouter(prefix="/analytics", tags=["ANALYTICS"])
router.include_router(performance.router)
router.include_router(risk.router)
router.include_router(portfolio.router)
