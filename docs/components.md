# Components

This document details every module and component in the Link Forge application.

---

## Authentication (`app/auth/`)

### `dependencies.py` — FastAPI Auth Dependency

Provides `get_current_user()`, a FastAPI `Depends` callable used to protect routes:

1. Extracts the Bearer token from the `Authorization` header via `HTTPBearer()`
2. Decodes the JWT using `decode_token()`
3. Validates the token type is `"access"` (rejects refresh tokens)
4. Looks up the user by `claims["sub"]` (user UUID)
5. Raises `401 Unauthorized` if the token is invalid/expired or the user no longer exists

### `jwt.py` — JWT Token Management

- **`create_access_token(user_id)`** — Creates a short-lived access token (default: 15 minutes)
- **`create_refresh_token(user_id)`** — Creates a long-lived refresh token (default: 7 days)
- **`decode_token(token)`** — Decodes and validates a JWT, returning the claims dict
- All tokens include `sub` (user ID), `type` (access/refresh), `iat`, and `exp` claims
- Signing algorithm: HS256 (configurable via `settings.jwt_algorithm`)
- Secret key: loaded from `settings.jwt_secret_key`

### `password.py` — Password Hashing

- **`hash_password(plain_password)`** — Hashes with bcrypt (12 rounds)
- **`verify_password(plain_password, password_hash)`** — Verifies a password against its hash

---

## Services (`app/services/`)

### `url_service.py` — URL Creation Logic

**`create_short_url(db, original_url, user_id, custom_alias, expires_at)`**

1. Validates the URL format (must have `http` or `https` scheme and a netloc)
2. Uses the `custom_alias` if provided, otherwise generates a random 7-char code
3. Attempts to insert the URL row; on `IntegrityError` (duplicate short code):
   - If using a custom alias: raises `ValueError` ("alias already taken")
   - If using a random code: regenerates and retries (up to `MAX_RETRIES = 5`)
4. Returns the created `Url` ORM instance

---

## Analytics (`app/analytics/`)

### `parser.py` — User-Agent Parsing

**`extract_browser_and_device(user_agent_string)`**

Uses the `user-agents` library to parse the `User-Agent` header:
- **Browser:** Extracted as `"{family} {version}"` (e.g., `"Chrome 91.0.4472"`)
- **Device:** Classified as one of: `mobile`, `tablet`, `desktop`, `other`

### `service.py` — Click Recording

**`record_click(db, url_id, request)`**

Creates a `Click` row capturing:
- `url_id` — The URL that was clicked
- `ip_address` — From `request.client.host`
- `browser` — Parsed from User-Agent
- `device` — Parsed from User-Agent
- `referrer` — From the `Referer` header

> Note: The click is added to the session but **not committed** — the caller (redirect handler) commits the transaction to batch the click insert with the click count update.

---

## Caching (`app/cache/`)

### `redis_client.py`

Singleton Redis client created from `settings.redis_url` with `decode_responses=True` (returns strings instead of bytes).

### `metrics.py`

Prometheus counters for cache observability:
- **`linkforge_cache_hits_total`** — Incremented when a redirect is served from Redis
- **`linkforge_cache_misses_total`** — Incremented when a redirect falls through to PostgreSQL

---

## Middleware (`app/middleware/`)

### `error_handlers.py` — Global Exception Handlers

Registered via `register_exception_handlers(app)` in the app factory:

| Exception | Status Code | Error Key | Description |
|---|---|---|---|
| `SQLAlchemyError` | 500 | `database_error` | Catches all database-layer exceptions |
| `Exception` | 500 | `internal_error` | Catch-all for unhandled exceptions (logged with traceback) |
| `RequestValidationError` | 422 | `validation_error` | Pydantic validation failures with per-field details |

All error responses follow a consistent JSON structure:
```json
{
  "error": "error_key",
  "message": "Human-readable message",
  "details": [{ "field": "body.email", "message": "..." }]
}
```

The `details` array is only present for validation errors.

### `rate_limit.py` — Rate Limiter

Configures a `SlowAPI` `Limiter` instance:
- **Key function:** `get_remote_address` (rate limits by client IP)
- **Default limit:** `{settings.rate_limit_per_minute}/minute` (default: 60/min)
- **Headers:** Rate limit headers are included in responses (`X-RateLimit-*`, `Retry-After`)
- The URL creation endpoint (`POST /api/v1/urls`) has a stricter per-route limit of `10/minute`

---

## Utilities (`app/utils/`)

### `short_code.py` — Short Code Generator

```python
def generate_short_code() -> str:
    return secrets.token_urlsafe(SHORT_CODE_LENGTH)[:SHORT_CODE_LENGTH]
```

- Uses `secrets.token_urlsafe()` for cryptographic randomness
- Length: 7 characters (URL-safe base64 alphabet: `A-Za-z0-9_-`)
- Collision probability is extremely low but handled by retry logic in `url_service.py`

### `logging.py` — Structured JSON Logging

**`JsonFormatter`** — Custom `logging.Formatter` that outputs JSON:
```json
{
  "level": "INFO",
  "message": "Application started",
  "logger": "linkforge",
  "time": "2026-07-27T10:30:00"
}
```

If an exception is present, an `"exception"` key is added with the formatted traceback.

**`configure_logging()`** — Sets up the JSON formatter on:
- The root logger
- Uvicorn loggers (`uvicorn`, `uvicorn.access`, `uvicorn.error`)

Called at module level in `app/main.py` before the app is created.

---

## Schemas (`app/schemas/`)

Pydantic models for request validation and response serialization.

### `auth.py`
| Schema | Fields | Validators |
|---|---|---|
| `RegisterRequest` | `username`, `email` (EmailStr), `password` | Password ≥ 8 chars |
| `LoginRequest` | `email` (EmailStr), `password` | — |
| `TokenResponse` | `access_token`, `refresh_token`, `token_type` | Default: `"bearer"` |
| `RefreshRequest` | `refresh_token` | — |

### `url.py`
| Schema | Fields | Validators |
|---|---|---|
| `UrlCreateRequest` | `original_url` (HttpUrl), `custom_alias` (optional), `expires_at` (optional) | Alias must be alphanumeric |
| `UrlResponse` | `id`, `short_code`, `short_url`, `original_url`, `is_active`, `click_count`, `expires_at`, `created_at` | `from_attributes = True` |
| `UrlUpdateRequest` | `original_url` (optional), `is_active` (optional), `expires_at` (optional) | — |

### `analytics.py`
| Schema | Fields |
|---|---|
| `DailyClicks` | `date` (str), `clicks` (int) |
| `AnalyticsSummary` | `total_clicks`, `daily_clicks` (list), `top_browsers` (dict), `top_devices` (dict), `top_referrers` (dict) |
