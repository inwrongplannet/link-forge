# Testing

Link Forge has a comprehensive testing strategy covering API tests, integration tests, manual shell scripts, and load tests.

---

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (client, db_session, auth helpers)
├── api/                     # API-level test suites
│   ├── test_analytics_endpoint.py  # Analytics flow & authorization
│   ├── test_rate_limit.py          # Rate limiting verification
│   ├── test_verification.py        # Auth, ownership, pagination tests
│   └── test_verifications.py       # Cache behavior & deactivation tests
├── integration/             # Integration tests
│   ├── test_auth_flow.py           # Register/login/token flow
│   └── test_urls_api.py            # URL CRUD & redirect
├── unit/                    # Unit tests (placeholder)
└── scripts/                 # Shell-based smoke tests
    ├── test_docker.sh              # Tests against Docker (port 8080)
    ├── test_endpoints.sh           # Tests against local server (port 8000)
    └── test_final.sh               # Extended endpoint tests
```

---

## Running Tests

### Local

```bash
# From project root with venv activated
PYTHONPATH=. pytest tests/ -s
```

### Docker

```bash
docker compose exec web pytest tests/ -s
```

### CI (GitHub Actions)

Tests run automatically on every push/PR to `main`. See `.github/workflows/ci.yml`.

---

## Test Fixtures (`conftest.py`)

### `setup_database` (session-scoped, autouse)

Runs `Base.metadata.create_all()` once per test session to ensure tables exist.

### `db_session`

Provides a SQLAlchemy session wrapped in a **transaction that is rolled back** after each test. This ensures complete test isolation without needing to truncate or recreate tables.

**How it works:**
1. Opens a raw connection from the engine
2. Begins a transaction
3. Binds a new session to that connection
4. Yields the session to the test
5. Closes the session, rolls back the transaction, closes the connection

### `reset_rate_limit` (autouse)

Disables the SlowAPI rate limiter for all tests (prevents `429` errors), re-enables after each test.

### `client`

Returns a `TestClient` that uses the transactional `db_session` instead of the real database session. Overrides `get_db` dependency.

### `auth_headers_for_two_users`

Registers and logs in two test users (`user_a`, `user_b`), returning their auth headers as a tuple. Useful for testing ownership/authorization logic.

---

## Test Suites

### API Tests

#### `test_analytics_endpoint.py`

End-to-end analytics flow:
1. Registers two users
2. User 1 creates a URL
3. Simulates 3 clicks with different User-Agent headers (Chrome/desktop, Safari/mobile, Firefox/desktop)
4. Verifies analytics: `total_clicks == 3`, correct device and browser breakdowns
5. Verifies User 2 cannot access User 1's analytics (returns 404)

#### `test_rate_limit.py`

1. Enables the rate limiter (normally disabled in tests)
2. Sends 10 URL creation requests (all succeed)
3. Sends an 11th request — asserts `429 Too Many Requests`
4. Verifies `Retry-After` header is present

#### `test_verification.py`

Comprehensive verification suite:
1. Register/login returns valid JWTs with correct claims
2. Tampered tokens are rejected with 401
3. User B cannot PATCH/DELETE User A's URLs (403)
4. URL listing with PATCH update works correctly
5. Dashboard supports combined search, sort, and pagination

#### `test_verifications.py`

Cache and deactivation behavior:
1. Creates a URL, clears its Redis cache
2. First redirect: cache miss → SQL SELECT + UPDATE (click count)
3. Second redirect: cache hit → no SQL SELECT, only UPDATE
4. Deactivates URL via PATCH → redirect returns 410 immediately

Uses SQLAlchemy `before_cursor_execute` event listener to count SQL queries.

### Integration Tests

#### `test_auth_flow.py`

- Register then login returns tokens
- Login with wrong password returns 401
- User B cannot edit User A's URL (403)

#### `test_urls_api.py`

- Create URL returns short code
- Invalid URL returns 422
- Redirect returns 302 with correct `Location` header
- Unknown short code returns 404

### Shell Scripts

Manual smoke test scripts that start a uvicorn server and exercise all endpoints via `curl`:

| Script | Target | Port | Tests |
|---|---|---|---|
| `test_endpoints.sh` | Local server | 8000 | Full CRUD + redirect + analytics |
| `test_docker.sh` | Docker container | 8080 | Same flow against Docker |
| `test_final.sh` | Local server | 8000 | Includes duplicate registration and invalid UUID tests |

---

## Load Tests

See `loadtests/` directory.

### Locust (`locustfile.py`)

- Each virtual user registers, logs in, and creates an initial URL
- **Task ratio:** 9:1 (redirects : URL creation)
- Wait time: 0.1–0.5 seconds between requests
- Run: `locust -f loadtests/locustfile.py --host http://localhost:8080`

### k6 (`redirect_test.js`)

- Ramp-up: 0→500 VUs over 30s
- Sustain: 500 VUs for 1 minute
- Ramp-down: 500→0 VUs over 30s
- Thresholds: p95 < 100ms, error rate < 1%
- Run: `k6 run loadtests/redirect_test.js`

### Performance Targets

| Metric | Target |
|---|---|
| Throughput | ≥ 1,000 RPS |
| p95 Latency | < 100ms |
| Error Rate | < 1% |
