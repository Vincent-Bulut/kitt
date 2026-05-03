# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KITT is a portfolio management application with a Python/FastAPI backend, a SvelteKit frontend, PostgreSQL database, and an nginx reverse proxy. All services are orchestrated via Docker Compose.

## Development Commands

### Backend (Python 3.12, managed with `uv`)

```bash
# Start only the database (for local dev)
docker-compose -f docker-compose.dev.yml up -d

# Run the API locally (from project root)
cd backend && uvicorn backend.api.main:api --host 0.0.0.0 --port 8000 --reload

# Install dependencies
cd backend && uv sync
# or
pip install -r backend/requirements.txt
```

The backend must be run from the **project root** (not from `backend/`) because imports use the `backend.api.*` package path and `PYTHONPATH` is set to `/app` in Docker.

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
docker-compose up          # prod-like: postgres + pgadmin + api + webapp + nginx
docker-compose up --build  # rebuild images
```

In prod Docker, nginx listens on port 80 (maps to internal port 5700), routes `/api/` → FastAPI on port 8000, and `/` → the static frontend served by nginx on port 80.

## Architecture

### Backend (`backend/`)

- **Entry point**: `backend/api/main.py` — creates the FastAPI `api` instance, registers CORS middleware, and mounts all routers.
- **Routers** (each in its own file under `backend/api/`):
  - `admin.py` — Portfolio CRUD (`/admin/portfolio`, `/admin/portfolios`)
  - `referential.py` — Asset listing, ETFBook static-data proxy, Excel upload/upsert into `assets` table (`/referential/`)
  - `analytics.py` — Yahoo Finance analytics: performance table, arithmetic return, cumulative returns series, drawdown analysis, annualized volatility, VaR/ES (`/analytics/yahoo/…`). All computation results are cached with `cachetools.TTLCache` (10 min).
  - `etfbook_primary.py` — Async proxy to ETFBook dynamic data API (NAV/AUM time series), chunked by 50 ISINs (`/etfbook/analytics/dynamic-data`)
- **DB layer**: SQLAlchemy ORM. `database.py` switches between `localhost` and the `postgres` Docker hostname based on the `ENV_KITT` env var (set to `prod` in Docker). Models live in `model.py` (Portfolio → Positions → Assets). Pydantic schemas in `schema.py`.
- **`utils.py`**: single helper `convert_to_timestamp()` used across analytics routes to normalise date strings.

### Frontend (`frontend/`)

- SvelteKit 5 with **adapter-static** — builds to `frontend/build/` as plain HTML/CSS/JS served by nginx in production.
- All API calls go through the `axios` instance in `src/lib/axiosAPI.js`, which reads `PUBLIC_APP_API_URL` from the SvelteKit public env (`frontend/.env` in dev).
- Route structure mirrors the backend domains: `/admin`, `/analytics/*`, `/referential/*`.

### Environment Variables

**Backend** (`backend/.env`):
| Variable | Purpose |
|---|---|
| `ETFBOOK_API_BASE_URL` | Base URL for the ETFBook external API |
| `ETFBOOK_REF_API_TOKEN` | Auth token for ETFBook API |
| `ETFBOOK_REF_API_BASE_URL` | Path for static data endpoint |
| `ETFBOOK_PRIMARY_TIME_SERIES` | Path for dynamic data endpoint |
| `ENV_KITT` | Set to `prod` to use the Docker DB hostname |

**Frontend** (`frontend/.env`):
| Variable | Purpose |
|---|---|
| `PUBLIC_APP_API_URL` | Backend API base URL (e.g. `http://localhost:8000/`) |

### Data Model

- **Portfolio**: top-level entity with date range and optional manager
- **Assets**: ETF/stock reference data keyed by `symbol` (ticker), with ISIN, currency, fee, and up to 4-level category taxonomy
- **Positions**: join between Portfolio and Assets with a quantity (`qte`)
