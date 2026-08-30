# Troubleshooting — Common Errors & Fixes

This document covers common errors encountered during development, testing, and deployment of Link Forge, along with their solutions.

---

## Database Errors

### `sqlalchemy.exc.OperationalError: connection refused`

**Cause:** PostgreSQL is not running or the connection string is wrong.

**Fix:**
1. Verify PostgreSQL is running: `pg_isready -h localhost -p 5432`
2. Check the `DATABASE_URL` in your `.env` file matches your PostgreSQL credentials
3. For Docker: ensure the `db` service is healthy (`docker compose ps`)
4. For local dev: ensure you created the `link_forge` database:
   ```bash
   createdb link_forge
   ```

### `sqlalchemy.exc.IntegrityError: duplicate key value violates unique constraint`

**Cause:** Attempting to insert a duplicate `short_code`, `email`, or `username`.

**Fix:**
- For `short_code`: This is handled automatically by the retry logic in `url_service.py` (up to 5 retries). If using a custom alias, choose a different one.
- For `email`/`username`: The API returns `409 Conflict`. Use a different email or username.

### `psycopg.OperationalError: FATAL: database "link_forge" does not exist`

**Cause:** The database hasn't been created yet.

**Fix:**
```bash
createdb link_forge
# or via psql:
psql -c "CREATE DATABASE link_forge;"
```

---

## Redis Errors

### `redis.exceptions.ConnectionError: Error connecting to localhost:6379`

**Cause:** Redis server is not running.

**Fix:**
1. Start Redis: `redis-server` or `sudo systemctl start redis`
2. Verify: `redis-cli ping` should return `PONG`
3. Check `REDIS_URL` in `.env` matches your Redis instance

### Stale cache after URL update

**Cause:** The Redis cache key was not invalidated.

**Fix:** This should not happen in normal operation — `PATCH` and `DELETE` endpoints explicitly call `redis_client.delete(f"url:{short_code}")`. If you're modifying URLs directly in the database, manually flush the key:
```bash
redis-cli DEL "url:<short_code>"
```

---

## Authentication Errors

### `401 Unauthorized: Invalid or expired token`

**Cause:** The JWT access token has expired (default: 15 minutes) or is malformed.

**Fix:**
1. Use the refresh endpoint to get a new access token:
   ```bash
   curl -X POST /api/v1/auth/refresh \
     -H "Content-Type: application/json" \
     -d '{"refresh_token": "<your_refresh_token>"}'
   ```
2. If the refresh token is also expired (default: 7 days), re-login.

### `401 Unauthorized: Wrong token type`

**Cause:** A refresh token was used where an access token is expected (or vice versa).

**Fix:** Ensure you're using the `access_token` in the `Authorization: Bearer` header, and the `refresh_token` only in the `/api/v1/auth/refresh` body.

### `403 Forbidden: You do not own this URL`

**Cause:** Attempting to update or delete a URL owned by a different user.

**Fix:** This is working as intended. Users can only modify their own URLs. Verify the URL ID belongs to the authenticated user.

---

## Rate Limiting

### `429 Too Many Requests`

**Cause:** The client IP has exceeded the rate limit.

**Fix:**
1. Wait for the duration specified in the `Retry-After` response header
2. The default global limit is 60 requests/minute; URL creation is limited to 10/minute
3. For testing, rate limiting can be disabled:
   ```python
   from app.middleware.rate_limit import limiter
   limiter.enabled = False
   ```

---

## Migration Errors

### `alembic.util.exc.CommandError: Can't locate revision`

**Cause:** The database's `alembic_version` table points to a revision that doesn't exist in the `migrations/versions/` directory.

**Fix:**
```bash
# Check current revision
alembic current

# If needed, stamp to a known revision
alembic stamp head
```

### `alembic.util.exc.CommandError: Target database is not up to date`

**Cause:** There are unapplied migrations.

**Fix:**
```bash
alembic upgrade head
```

---

## Testing Errors

### `429 Too Many Requests` in test suite

**Cause:** Rate limiting is active during tests.

**Fix:** The test `conftest.py` includes an `autouse` fixture that disables the rate limiter. If you're running tests outside of pytest, disable it manually:
```python
from app.middleware.rate_limit import limiter
limiter.enabled = False
```

### `FAILED: assert response.status_code == 201` on URL creation

**Common causes:**
1. Not authenticated — ensure you include the `Authorization: Bearer <token>` header
2. Invalid URL format — must be a valid HTTP/HTTPS URL
3. Duplicate custom alias — use a unique alias

### Database state leaking between tests

**Cause:** Tests are not properly rolling back transactions.

**Fix:** Always use the `client` and `db_session` fixtures from `conftest.py`. The `db_session` fixture wraps each test in a transaction that is rolled back after the test completes. The `get_async_db` override ensures async route handlers use the same rolled-back session.

---

## Async & Worker Issues

### `RuntimeError: asyncio is already running`

**Cause:** Trying to call `asyncio.run()` or start a new event loop inside an already-running loop.

**Fix:** This typically happens when mixing sync and async Redis clients. Always use `async_redis_client` (from `app/cache/redis_client.py`) in async route handlers and the sync `redis_client` in background tasks or scripts.

### Tests: `No async session override found`

**Cause:** The `get_async_db` override fixture is not being applied.

**Fix:** Ensure the `get_async_db` fixture in `conftest.py` has `autouse=True` and is at the correct scope. The fixture must yield an `AsyncSession` backed by the sync `db_session` transaction.

### Multiple flush workers running simultaneously

**Cause:** Each uvicorn worker starts its own `asyncio.create_task` for the flush worker. With `--workers 4`, four flush workers run concurrently.

**Fix:** This is expected behavior — each worker drains its own portion of the Redis buffer. The `drain_click_buffer` function uses atomic Redis operations (`LLEN` + `LPOP`) so concurrent workers won't double-count events.

### `Connection pool exhausted` with multiple workers

**Cause:** Each worker creates its own connection pool; with 4 workers and default pool size of 5, you may exhaust connections under load.

**Fix:** Increase the pool size in `app/database/session.py` or reduce the number of workers:
```python
async_engine = create_async_engine(
    AsyncDATABASE_URL,
    pool_size=10,  # default is 5
    max_overflow=20,
)
```

---

## Docker Errors

### `docker compose up` hangs waiting for database

**Cause:** The `db` service health check is failing.

**Fix:**
1. Check the database logs: `docker compose logs db`
2. Ensure port 5433 is not already in use: `lsof -i :5433`
3. Remove stale volumes and rebuild:
   ```bash
   docker compose down -v
   docker compose up --build
   ```

### Application can't connect to Redis/PostgreSQL in Docker

**Cause:** The application is using `localhost` instead of the Docker service names.

**Fix:** In Docker Compose, services communicate via service names, not `localhost`. Ensure the environment variables use:
- `DATABASE_URL=postgresql+psycopg://link_forge_user:password123@db:5432/link_forge`
- `REDIS_URL=redis://redis:6379/0`

### Port conflicts

**Cause:** The mapped ports are already in use on the host.

**Fix:** The Docker Compose port mappings are:
| Service | Host Port | Container Port |
|---|---|---|
| web | 8080 | 8000 |
| db | 5433 | 5432 |
| redis | 6380 | 6379 |
| prometheus | 9090 | 9090 |
| grafana | 3001 | 3000 |

Change the host port in `docker-compose.yml` if conflicts exist.

---

## URL Redirect Issues

### `404 Not Found: Short URL not found`

**Cause:** The short code does not exist in the database.

**Fix:** Verify the short code is correct and the URL hasn't been deleted.

### `410 Gone: This link has been deactivated`

**Cause:** The URL's `is_active` field is `false` (deactivated via `PATCH`).

**Fix:** Re-activate the URL:
```bash
curl -X PATCH /api/v1/urls/<url_id> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"is_active": true}'
```

### `410 Gone: This link has expired`

**Cause:** The URL's `expires_at` timestamp is in the past.

**Fix:** Update the expiration or remove it:
```bash
curl -X PATCH /api/v1/urls/<url_id> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"expires_at": null}'
```
