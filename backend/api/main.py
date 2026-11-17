import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import observability
from backend.api.admin import router as admin_router
from backend.api.analytics import router as analytics_router
from backend.api.referential import router as referential_router
from backend.api.transactions import router as transactions_router

observability.configure_logging()

api = FastAPI(
    title="KITT API",
    description="Portfolio management and quantitative analytics API.",
    version="0.1.0",
)

# Comma-separated list of allowed origins, e.g. "http://localhost:5173,http://localhost"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost").split(",")
    if origin.strip()
]

api.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

observability.install(api)

api.include_router(admin_router)
api.include_router(referential_router)
api.include_router(analytics_router)
api.include_router(transactions_router)


@api.get("/health", tags=["HEALTH"])
def health():
    return {"status": "ok"}
