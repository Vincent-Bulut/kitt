# KITT — Portfolio Analytics

[![CI](https://github.com/Vincent-Bulut/kitt/actions/workflows/ci.yml/badge.svg)](https://github.com/Vincent-Bulut/kitt/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![SvelteKit](https://img.shields.io/badge/SvelteKit-5-ff3e00)

KITT is a self-hosted portfolio management and risk analytics platform for ETF and equity portfolios.
It tracks portfolios and transactions, maintains an ETF reference universe, and runs quantitative
analytics (risk, performance, optimization) on market data from Yahoo Finance.

## Features

**Portfolio management**
- Portfolios, transactions (BUY/SELL with fees) and a computed positions view with weighted-average cost,
  realized / unrealized P&L, weights and estimated TER cost
- ETF reference data: Excel bulk upsert into PostgreSQL, Euronext scraping of PEA-eligible ETFs and
  detection of ISINs missing from the universe

**Performance & risk**
- Period performance table (1D → 5Y, YTD), arithmetic and cumulative returns
- Drawdown analysis: max drawdown path (peak / trough / recovery), drawdown episodes and durations
- Annualized volatility (daily / weekly / monthly, log or arithmetic returns)
- Value-at-Risk and Expected Shortfall: historical, Gaussian and Cornish-Fisher, per asset and at portfolio level
- Correlation matrix and diversification metrics, PCA risk decomposition
- Regression against a benchmark (beta, alpha, R²) with FX conversion to a common base currency

**Portfolio construction**
- Efficient frontier, minimum-variance and maximum-Sharpe portfolios with weight bounds
- Black-Litterman posterior returns with user views
- Random portfolio sampler and Monte Carlo simulation (geometric Brownian motion)

## Architecture

```
                ┌──────────────────────────── docker compose ────────────────────────────┐
 Browser ──────▶│ nginx :80 ──▶ webapp (SvelteKit static build)                          │
    │           │                                                                        │
    └──────────▶│ api :8000 (FastAPI) ──▶ PostgreSQL ◀── pgAdmin (127.0.0.1 only)        │
                │      │                                                                 │
                └──────┼─────────────────────────────────────────────────────────────────┘
                       ├──▶ Yahoo Finance (prices, FX)  — TTL-cached in memory
                       └──▶ Euronext (PEA ETF list)
```

| Layer | Stack |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (typed ORM) |
| Analytics | pandas, NumPy, SciPy (optimization, statistics), yfinance |
| Database | PostgreSQL |
| Frontend | SvelteKit 5 (static adapter), TypeScript |
| Tooling | uv, ruff, pytest, GitHub Actions, Docker (multi-stage, non-root) |

```
backend/
  api/
    main.py           FastAPI app, CORS, router registration, /health
    admin.py          portfolio CRUD
    transactions.py   transactions + positions view (WAC accounting)
    referential.py    asset universe, Excel upload, PEA referential
    analytics/        quantitative analytics, layered:
      routes/           thin FastAPI routers (performance, risk, portfolio)
      services/         orchestration: market data + computation + caching
      quant/            pure functions: returns, drawdown, risk, optimization, PCA, regression, simulation
      market_data.py    Yahoo Finance prices and FX (the only network I/O)
      schemas.py        Pydantic request / response models
    model.py          SQLAlchemy models (Portfolio, Assets, Positions, Transaction)
    schema.py         Pydantic request / response schemas
  migrations/         Alembic revisions (applied automatically when the API container starts)
  migrate.py          stamps pre-Alembic databases, then upgrades to head
  tests/              pytest suite (no network, no Postgres needed)
frontend/             SvelteKit app (admin, analytics, portfolio, referential pages)
```

## Getting started

### Full stack with Docker

```bash
cp .env.example .env           # set Postgres / pgAdmin credentials
touch backend/.env             # optional external API settings, see below
docker compose up --build
```

- App: http://localhost
- API docs (OpenAPI): http://localhost:8000/docs

### Local development

Requires [uv](https://docs.astral.sh/uv/) and Node 22+.

```bash
# Database only (Postgres on :5433, pgAdmin on :8081)
docker compose -f docker-compose.dev.yml up -d

# API — run from the project root
uv sync --project backend
uv run --project backend --env-file backend/.env python -m backend.migrate   # apply migrations
uv run --project backend --env-file backend/.env uvicorn backend.api.main:api --reload

# Frontend
cd frontend && npm install && npm run dev      # http://localhost:5173
```

### Database migrations

The schema is managed with Alembic; monetary columns are exact `NUMERIC`.

```bash
# After changing backend/api/model.py
uv run --project backend --env-file backend/.env alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
uv run --project backend --env-file backend/.env python -m backend.migrate
```

### Configuration

| File | Variables |
|---|---|
| `.env` (Compose) | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD`, `CORS_ORIGINS` |
| `backend/.env` | `DATABASE_*` for local runs, optional reference-data API settings |
| `frontend/.env` | `PUBLIC_APP_API_URL` (e.g. `http://localhost:8000/`) |

Secrets are never committed nor baked into images.

## Quality

```bash
uv run --project backend ruff check backend
uv run --project backend pytest
```

The test suite checks the quantitative core against closed-form results and simulated data
(VaR/ES estimators, drawdowns, volatility scaling, mean-variance optimizers, WAC position accounting)
and exercises the CRUD endpoints against an in-memory SQLite database. CI runs lint, tests, the
frontend build, and replays the migrations on PostgreSQL (upgrade, `alembic check` for drift against
the models, downgrade / upgrade round trip) on every push.

## Known limitations & roadmap

This is a personal project used as a sandbox for portfolio analytics. Next steps:

- [ ] Merge the remaining Yahoo download helpers into a single market-data client
- [ ] Persist daily prices in PostgreSQL through a scheduled, incremental ingestion job instead of fetching on demand
- [ ] Shared cache (Redis) instead of per-process in-memory caches
- [ ] Split the portfolio page into components and fix `svelte-check` type errors
- [ ] Authentication
