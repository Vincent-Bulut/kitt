# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KITT is a portfolio management application with a Python/FastAPI backend, a SvelteKit frontend, PostgreSQL database, and an nginx reverse proxy. All services are orchestrated via Docker Compose.

## Development Commands

### Backend (Python 3.12, managed with `uv`)

```bash
# Start only the database (for local dev, Postgres on localhost:5433, pgAdmin on :8081)
docker compose -f docker-compose.dev.yml up -d

# Install dependencies (creates backend/.venv)
uv sync --project backend

# Run the API locally — from the PROJECT ROOT, loading backend/.env
uv run --project backend --env-file backend/.env uvicorn backend.api.main:api --reload

# Add a dependency (updates backend/pyproject.toml + backend/uv.lock)
uv add --project backend <package>
uv add --project backend --dev <package>   # dev-only (pytest, ruff…), excluded from the Docker image

# Database migrations (Alembic, config in backend/alembic.ini, revisions in backend/migrations/versions/)
uv run --project backend --env-file backend/.env python -m backend.migrate          # stamp legacy DB if needed + upgrade head
uv run --project backend --env-file backend/.env alembic -c backend/alembic.ini revision --autogenerate -m "..."
uv run --project backend --env-file backend/.env alembic -c backend/alembic.ini check  # models vs DB drift

# Lint / tests
uv run --project backend ruff check backend
uv run --project backend pytest
```

The backend must be run from the **project root** (not from `backend/`) because imports use the `backend.api.*` package path and `PYTHONPATH` is set to `/app` in Docker. Nothing in the code loads `.env` files: variables come from `--env-file` locally and from `env_file` in Docker Compose.

### Frontend (SvelteKit + Vite)

```bash
cd frontend
npm install
npm run dev          # dev server on :5173
npm run build        # static build to frontend/build/
npm run check        # TypeScript + Svelte type checking
```

### Full Stack (Docker)

```bash
docker compose up          # prod-like: postgres + pgadmin + api + webapp + nginx
docker compose up --build  # rebuild images
```

Requires a root `.env` (copy `.env.example`) for Postgres/pgAdmin credentials.

In prod Docker, nginx listens on port 80 (maps to internal port 5700), routes `/api/` → FastAPI on port 8000, and `/` → the static frontend served by nginx on port 80. Host-published ports: 80 (nginx), 8000 (API — the frontend calls `http://localhost:8000/` directly), and 127.0.0.1-only 5432 (Postgres) and 8080 (pgAdmin). The frontend container publishes no port.

Images: the API image (`backend/Dockerfile`) is built from the project root with `uv sync --locked --no-dev` and runs as a non-root user; `.env` files are excluded from build contexts (`.dockerignore`). The frontend image is a two-stage build (`npm ci` + `vite build`, then nginx); `frontend/.env` is kept in its build context because `PUBLIC_*` variables are inlined at build time.

## Architecture

### Backend (`backend/`)

- **Entry point**: `backend/api/main.py` — creates the FastAPI `api` instance, registers CORS middleware (origins from `CORS_ORIGINS`), mounts all routers and exposes `/health`.
- **Routers** (each in its own file under `backend/api/`):
  - `admin.py` — Portfolio CRUD (`/admin/portfolio`, `/admin/portfolios`)
  - `referential.py` — Asset listing, ETFBook static-data proxy, Excel upload/upsert into `assets` table (`/referential/`)
  - `analytics/` — Yahoo Finance analytics package (`/analytics/yahoo/…`), layered so that dependencies only point downwards:
    - `routes/{performance,risk,portfolio}.py` — thin routers, aggregated in `analytics/__init__.py` under the `/analytics` prefix
    - `services/{performance,risk,portfolio,optimization}.py` — `run_*` use cases: download data, call `quant`, cache results in `cachetools.TTLCache` (10 min)
    - `quant/` — pure functions (returns, drawdown, VaR/ES, optimization, PCA, regression, simulation): no FastAPI, no network, no cache; this is what the unit tests target
    - `market_data.py` — all Yahoo Finance / FX downloads; `schemas.py` — Pydantic models
  - `transactions.py` — Transaction CRUD and the computed positions view (weighted-average cost, P&L) (`/portfolios/{id}/…`, `/transactions/…`)
  - `etfbook_primary.py` — Async proxy to ETFBook dynamic data API (NAV/AUM time series), chunked by 50 ISINs. Not mounted in `main.py`.
- **DB layer**: SQLAlchemy ORM. `database.py` builds the connection URL from `DATABASE_USER/PASSWORD/HOST/PORT/NAME` (defaults: `localhost:5433`, the dev DB); Docker Compose overrides them to target the `postgres` service. Models live in `model.py` (Portfolio → Positions → Assets). Pydantic schemas in `schema.py`.
- **`utils.py`**: single helper `convert_to_timestamp()` used across analytics routes to normalise date strings.
- **Tests** (`backend/tests/`): pure-function tests for analytics/positions/PEA parsing and HTTP tests that mount routers on a FastAPI app with `get_db` overridden to in-memory SQLite (no Postgres needed; migrations are exercised by the `migrations` CI job instead). Ruff and pytest config live in `backend/pyproject.toml`; CI is `.github/workflows/ci.yml`.

### Frontend (`frontend/`)

- SvelteKit 5 with **adapter-static** — builds to `frontend/build/` as plain HTML/CSS/JS served by nginx in production.
- All API calls go through the `axios` instance in `src/lib/axiosAPI.js`, which reads `PUBLIC_APP_API_URL` from the SvelteKit public env (`frontend/.env` in dev).
- Route structure mirrors the backend domains: `/admin`, `/analytics/*`, `/referential/*`.

### Environment Variables

**Docker Compose** (root `.env`, git-ignored — template in `.env.example`):
| Variable | Purpose |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres credentials (also injected into the API container as `DATABASE_*`) |
| `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` | pgAdmin login |
| `CORS_ORIGINS` | Comma-separated origins allowed by the API (default `http://localhost,http://localhost:5173`) |

**Backend** (`backend/.env`, git-ignored, never baked into the image):
| Variable | Purpose |
|---|---|
| `ETFBOOK_API_BASE_URL` | Base URL for the ETFBook external API |
| `ETFBOOK_REF_API_TOKEN` | Auth token for ETFBook API |
| `ETFBOOK_REF_API_BASE_URL` | Path for static data endpoint |
| `ETFBOOK_PRIMARY_TIME_SERIES` | Path for dynamic data endpoint |
| `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` | DB connection for local runs (overridden by Compose in Docker) |
| `ENV_KITT` | Set to `prod` in Docker (informational) |

**Frontend** (`frontend/.env`):
| Variable | Purpose |
|---|---|
| `PUBLIC_APP_API_URL` | Backend API base URL (e.g. `http://localhost:8000/`) |

### Data Model

- **Portfolio**: top-level entity with date range and optional manager
- **Assets**: ETF/stock reference data keyed by `symbol` (ticker), with ISIN, currency, fee, and up to 4-level category taxonomy
- **Positions**: join between Portfolio and Assets, unique per (portfolio, symbol); currently unused by the API
- **Transaction**: BUY/SELL with quantity, price, fee, amount; the positions view is computed from transactions

Schema changes go through Alembic, never `create_all()`: edit `model.py`, autogenerate a revision, review it. Money/quantity columns are `Numeric(..., asdecimal=False)` so the DB stores exact decimals while Python code keeps working with floats. The API container runs `python -m backend.migrate` before uvicorn (see `backend/Dockerfile`).
