# Database

Link Forge uses **PostgreSQL 15** as its primary data store, accessed via **SQLAlchemy 2.0** ORM with the **psycopg** (v3) async-capable driver.

## Connection Configuration

Database configuration is managed through `app/database/config.py` using `pydantic-settings`.

### Settings Class

```python
class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://abhishek:user1234@127.0.0.1:5432/link_forge"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 60
    base_url: str = "http://localhost:8000"
    jwt_secret_key: str = "supersecretkey_please_change_in_production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
```

Settings are loaded from environment variables and `.env` file (via `SettingsConfigDict`).

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg://link_forge_user:password123@127.0.0.1:5433/link_forge` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6380/0` |
| `RATE_LIMIT_PER_MINUTE` | Global rate limit | `60` |
| `BASE_URL` | Public base URL for short links | `http://localhost:8000` |
| `JWT_SECRET_KEY` | Secret key for JWT signing | `supersecretkey_please_change_in_production` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL in minutes | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL in days | `7` |

## Engine & Session

Defined in `app/database/session.py`:

```python
# Sync engine — used by flush worker, bootstrap, and test fixtures
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine — used by async route handlers via greenlet-based AsyncSession
async_engine = create_async_engine(AsyncDATABASE_URL, future=True, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
```

- **Sync `engine`**: Direct psycopg3 driver. Used by the flush worker and Alembic migrations.
- **Async `async_engine`**: Uses `sqlalchemy.ext.asyncio` with psycopg3 via a greenlet shim. Non-blocking I/O for async route handlers.
- **`pool_pre_ping=True`**: Validates connections before use, recovering from stale connections.
- **`future=True`**: Uses SQLAlchemy 2.0-style engine.
- **`autocommit=False, autoflush=False`**: Explicit transaction control.

### Dependency Injection

The `get_db()` generator is used as a FastAPI dependency to provide scoped sessions for sync code paths (flush worker, health checks):

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

The `get_async_db()` async generator is the primary dependency for async route handlers:

```python
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

Override `get_async_db` in tests to provide a sync-backed `AsyncSession` that uses the transactional `db_session` fixture.

## Schema Bootstrap

On application startup, `app/database/bootstrap.py` calls:

```python
def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
```

This creates any missing tables from the ORM model definitions. For production, Alembic migrations should be used instead (see [migrations.md](./migrations.md)).

---

## Data Models

All models inherit from `app.database.session.Base` (SQLAlchemy `DeclarativeBase`) and use the modern `Mapped` + `mapped_column` syntax.

### `users` Table (`app/models/user.py`)

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | Primary key, auto-generated (`uuid4`) |
| `username` | `VARCHAR(50)` | Unique, indexed |
| `email` | `VARCHAR(255)` | Unique, indexed |
| `password_hash` | `VARCHAR(255)` | Stores bcrypt hash |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Server default: `now()` |

### `urls` Table (`app/models/url.py`)

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | Primary key, auto-generated (`uuid4`) |
| `user_id` | `UUID` | Foreign key → `users.id`, nullable, indexed (`ix_urls_user_id`) |
| `original_url` | `TEXT` | The destination URL |
| `short_code` | `VARCHAR(16)` | Unique, indexed (`ix_urls_short_code`) |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | Nullable |
| `click_count` | `INTEGER` | Default: `0` |
| `is_active` | `BOOLEAN` | Default: `true` |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Server default: `now()` |

**Indexes:**
- `ix_urls_short_code` — Unique index on `short_code` (primary lookup for redirects)
- `ix_urls_user_id` — Non-unique index on `user_id` (dashboard queries)

### `clicks` Table (`app/models/click.py`)

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | Primary key, auto-generated (`uuid4`) |
| `url_id` | `UUID` | Foreign key → `urls.id`, indexed |
| `ip_address` | `VARCHAR(64)` | Nullable |
| `browser` | `VARCHAR(64)` | Nullable (parsed from User-Agent) |
| `device` | `VARCHAR(64)` | Nullable (`mobile`, `tablet`, `desktop`, `other`) |
| `referrer` | `TEXT` | Nullable (from `Referer` header) |
| `clicked_at` | `TIMESTAMP WITH TIME ZONE` | Server default: `now()` |

---

## Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────────┐
│    users     │       │      urls        │       │     clicks       │
├──────────────┤       ├──────────────────┤       ├──────────────────┤
│ id       (PK)│◄──────│ user_id    (FK)  │       │ id           (PK)│
│ username     │       │ id         (PK)  │◄──────│ url_id       (FK)│
│ email        │       │ original_url     │       │ ip_address       │
│ password_hash│       │ short_code       │       │ browser          │
│ created_at   │       │ expires_at       │       │ device           │
└──────────────┘       │ click_count      │       │ referrer         │
                       │ is_active        │       │ clicked_at       │
                       │ created_at       │       └──────────────────┘
                       └──────────────────┘

Relationships:
  users 1──────N urls      (one user has many URLs)
  urls  1──────N clicks    (one URL has many clicks)
```

## Redis Cache

Redis is used as a **cache-aside** store for redirect lookups.

- **Client:** `app/cache/redis_client.py` — two singleton instances:
  - `redis_client` — `redis.Redis` (sync), used by flush worker and cache invalidation
  - `async_redis_client` — `redis.asyncio.Redis` (async), used by async route handlers
- **Key format:** `url:{short_code}`
- **Value:** JSON string `{"id": "...", "original_url": "...", "is_active": true/false}`
- **TTL:** 300 seconds (5 minutes)
- **Invalidation:** Cache keys are deleted on `PATCH` or `DELETE` of the URL

### Cache Metrics

Two Prometheus counters track cache performance (`app/cache/metrics.py`):
- `linkforge_cache_hits_total` — Redirect served from Redis
- `linkforge_cache_misses_total` — Redirect required PostgreSQL lookup
