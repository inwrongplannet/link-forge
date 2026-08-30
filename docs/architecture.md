# Architecture

Link Forge is a URL shortener API built with **FastAPI** (Python 3.12). It follows a layered architecture separating concerns into routes, services, data access, caching, and authentication.

## High-Level Overview

```
Client Request
    │
    ▼
┌──────────────────────────────────────────┐
│              FastAPI App                 │
│  (app/main.py — create_app factory)      │
├──────────────────────────────────────────┤
│  Middleware Layer                        │
│  ├─ SlowAPI Rate Limiting               │
│  ├─ Prometheus Instrumentator           │
│  └─ Global Exception Handlers           │
├──────────────────────────────────────────┤
│  API Routers (app/api/)                  │
│  ├─ auth.py     → /api/v1/auth/*        │
│  ├─ urls.py     → /api/v1/urls/*        │
│  ├─ analytics.py→ /api/v1/urls/*/analytics│
│  ├─ redirect.py → /{short_code}         │
│  └─ health.py   → /health, /ready       │
├──────────────────────────────────────────┤
│  Auth Layer (app/auth/)                  │
│  ├─ dependencies.py (get_current_user)   │
│  ├─ jwt.py (token creation/decode)       │
│  └─ password.py (bcrypt hash/verify)     │
├──────────────────────────────────────────┤
│  Service Layer (app/services/)           │
│  └─ url_service.py (URL creation logic)  │
├──────────────────────────────────────────┤
│  Analytics Layer (app/analytics/)        │
│  ├─ service.py  (record_click fallback)  │
│  └─ parser.py   (user-agent parsing)     │
├──────────────────────────────────────────┤
│  Caching Layer (app/cache/)              │
│  ├─ redis_client.py  (Redis singleton)   │
│  ├─ click_buffer.py  (buffer_click)      │
│  ├─ flush_worker.py  (batch Postgres)    │
│  └─ metrics.py       (Prometheus)        │
├──────────────────────────────────────────┤
│  Data Layer                              │
│  ├─ Models    (app/models/)              │
│  ├─ Schemas   (app/schemas/)             │
│  └─ Database  (app/database/)            │
├──────────────────────────────────────────┤
│  Infrastructure                          │
│  ├─ PostgreSQL (via SQLAlchemy + psycopg)│
│  ├─ Redis      (cache + click buffer)    │
│  ├─ Prometheus (metrics scraping)        │
│  └─ Grafana    (dashboards)              │
└──────────────────────────────────────────┘
```

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Web Framework | FastAPI | 0.139.2 |
| ASGI Server | Uvicorn | 0.51.0 |
| ORM | SQLAlchemy | 2.0.51 |
| Database | PostgreSQL | 15 |
| DB Driver | psycopg | 3.3.4 |
| Migrations | Alembic | 1.18.5 |
| Cache | Redis | 7 (alpine) |
| Python Redis | redis-py | 8.0.1 |
| Auth | PyJWT + bcrypt | 2.13.0 / 5.0.0 |
| Validation | Pydantic | 2.13.4 |
| Rate Limiting | SlowAPI | 0.1.10 |
| Metrics | prometheus-fastapi-instrumentator, prometheus-client | — |
| Testing | pytest + httpx | 8.2.2 / 0.27.0 |
| Load Testing | Locust, k6 | — |
| Containerization | Docker + Docker Compose | — |
| CI | GitHub Actions | — |

## Application Factory

The app is created via a factory function `create_app()` in `app/main.py`. This:

1. Creates a `FastAPI` instance with a `lifespan` context manager
2. On startup, calls `initialize_database()` to run `Base.metadata.create_all()`
3. Starts the click flush worker as an `asyncio.create_task` (not a thread)
4. Instruments the app with Prometheus via `Instrumentator()`
5. Includes all API routers (`health`, `urls`, `redirect`, `auth`, `analytics`)
6. Registers global exception handlers for `SQLAlchemyError`, `RequestValidationError`, and `Exception`
7. Configures SlowAPI rate limiting middleware

Uvicorn runs with `--workers 4` in production, each worker running its own asyncio event loop with its own flush worker task.

## Directory Structure

```
link-forge/
├── app/
│   ├── __init__.py
│   ├── main.py              # App factory, lifespan, middleware registration
│   ├── api/                 # Route handlers
│   │   ├── analytics.py     # GET /{url_id}/analytics
│   │   ├── auth.py          # POST /register, /login, /refresh
│   │   ├── health.py        # GET /health, /ready
│   │   ├── redirect.py      # GET /{short_code} → 302 redirect
│   │   └── urls.py          # CRUD for shortened URLs
│   ├── analytics/           # Click analytics logic
│   │   ├── parser.py        # User-agent → browser + device
│   │   └── service.py       # record_click()
│   ├── auth/                # Authentication utilities
│   │   ├── dependencies.py  # FastAPI Depends(get_current_user)
│   │   ├── jwt.py           # JWT create/decode
│   │   └── password.py      # bcrypt hash/verify
│   ├── cache/               # Redis caching + click buffering
│   │   ├── click_buffer.py  # buffer_click(), buffer_click_async() — Redis pipeline
│   │   ├── flush_worker.py  # Background batch flush (sync thread + async task)
│   │   ├── metrics.py       # Prometheus cache + click-buffer counters
│   │   └── redis_client.py  # Redis singleton (sync + async_redis_client)
│   ├── core/                # Reserved for future core config
│   ├── database/            # Database connection & config
│   │   ├── bootstrap.py     # create_all tables on startup
│   │   ├── config.py        # Settings (pydantic-settings)
│   │   └── session.py       # Engine + AsyncEngine, SessionLocal + AsyncSessionLocal
│   ├── middleware/           # Middleware & error handling
│   │   ├── error_handlers.py# Global exception handlers
│   │   └── rate_limit.py    # SlowAPI limiter instance
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── click.py         # Click model
│   │   ├── url.py           # Url model
│   │   └── user.py          # User model
│   ├── schemas/             # Pydantic request/response schemas
│   │   ├── analytics.py     # AnalyticsSummary, DailyClicks
│   │   ├── auth.py          # Register, Login, Token schemas
│   │   └── url.py           # UrlCreate, UrlResponse, UrlUpdate
│   ├── services/            # Business logic
│   │   └── url_service.py   # create_short_url()
│   └── utils/               # Shared utilities
│       ├── logging.py       # JSON log formatter
│       └── short_code.py    # Cryptographic short code generator
├── migrations/              # Alembic migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── tests/                   # Test suites
│   ├── api/                 # API-level tests
│   ├── integration/         # Integration tests
│   ├── scripts/             # Shell-based test scripts
│   └── unit/                # Unit tests (placeholder)
├── loadtests/               # Performance tests
│   ├── locustfile.py        # Locust load test
│   └── redirect_test.js     # k6 load test
├── .github/workflows/ci.yml # GitHub Actions CI
├── Dockerfile               # Production container image
├── docker-compose.yml       # Full-stack local environment
├── prometheus.yml           # Prometheus scrape config
├── alembic.ini              # Alembic configuration
├── requirements.txt         # Pinned Python dependencies
├── seed.py                  # Data seeder for load tests
└── .env                     # Local environment variables
```

## Key Design Decisions

### Cache-Aside Pattern with Redis-Buffered Clicks
Redirects use a **cache-aside** (lazy-loading) strategy with Redis. On a redirect request:
1. Check Redis for `url:{short_code}` → if found, serve from cache (no DB SELECT)
2. On cache miss, query PostgreSQL, populate Redis with a 300-second TTL
3. On URL update/delete, the corresponding cache key is invalidated immediately

Click data is **buffered in Redis** on every redirect (cache hit or miss) via `buffer_click()`, which uses a single Redis pipeline to `INCR` the click counter and `RPUSH` the event details. A background flush worker drains these buffers every 10 seconds and batch-writes to Postgres. This removes all DB writes from the redirect hot path, eliminating row-lock contention.

Unknown short codes are cached with a 60-second negative cache (`__miss__` sentinel) to prevent Postgres stampedes.

### Async Concurrency with Multi-Worker Scaling
All route handlers are `async def` and use `redis.asyncio` for non-blocking Redis I/O. The redirect hot path touches only Redis (no DB interaction on cache hits). A background `asyncio` task runs the click flush worker, which drains buffered clicks to Postgres using its own sync SQLAlchemy engine. Uvicorn runs with `--workers 4` for multi-process scaling, with each worker sharing the same PostgreSQL and Redis backends.

SQLAlchemy sessions are provided via `AsyncSession` backed by a greenlet-based async engine (wrapping psycopg3's sync driver). The sync `get_db()` dependency is retained for the flush worker and bootstrap code.

### Short Code Generation
Short codes are generated using `secrets.token_urlsafe()` (cryptographically secure), truncated to 7 characters. On collision, the service retries up to 5 times with fresh codes.

### Structured Logging
All logs are emitted as JSON via a custom `JsonFormatter`, including uvicorn access/error logs. This makes log aggregation and parsing straightforward in production environments.
