# API Routes

All API routes are defined under `app/api/`. The application uses FastAPI's `APIRouter` to organize endpoints into logical groups.

## Base URLs

| Environment | Base URL |
|---|---|
| Local development | `http://localhost:8000` |
| Docker Compose | `http://localhost:8080` |

## Interactive Documentation

FastAPI auto-generates interactive API docs:
- **Swagger UI**: `{base_url}/docs`
- **ReDoc**: `{base_url}/redoc`

---

## Authentication (`app/api/auth.py`)

Prefix: `/api/v1/auth`

### `POST /api/v1/auth/register`

Register a new user account.

**Request Body:**
```json
{
  "username": "string (required)",
  "email": "string (valid email, required)",
  "password": "string (min 8 chars, required)"
}
```

**Responses:**
| Status | Description |
|---|---|
| `201 Created` | User created successfully. Returns `{id, username, email}`. |
| `409 Conflict` | Email or username already registered. |
| `422 Unprocessable Entity` | Validation error (e.g., password too short). |

---

### `POST /api/v1/auth/login`

Authenticate and receive JWT tokens.

**Request Body:**
```json
{
  "email": "string (required)",
  "password": "string (required)"
}
```

**Responses:**
| Status | Description |
|---|---|
| `200 OK` | Returns `{access_token, refresh_token, token_type}`. |
| `401 Unauthorized` | Invalid email or password. |

---

### `POST /api/v1/auth/refresh`

Exchange a refresh token for a new token pair.

**Request Body:**
```json
{
  "refresh_token": "string (required)"
}
```

**Responses:**
| Status | Description |
|---|---|
| `200 OK` | Returns new `{access_token, refresh_token, token_type}`. |
| `401 Unauthorized` | Invalid, expired, or wrong token type. |

---

## URL Management (`app/api/urls.py`)

Prefix: `/api/v1/urls`

> **All endpoints in this group require authentication** via `Authorization: Bearer <access_token>` header.

### `POST /api/v1/urls`

Create a new shortened URL.

**Rate Limit:** 10 requests per minute per IP.

**Request Body:**
```json
{
  "original_url": "string (valid HTTP/HTTPS URL, required)",
  "custom_alias": "string (alphanumeric only, optional)",
  "expires_at": "datetime (ISO 8601, optional)"
}
```

**Responses:**
| Status | Description |
|---|---|
| `201 Created` | URL created. Returns full `UrlResponse`. |
| `409 Conflict` | Custom alias is already taken, or invalid URL format. |
| `422 Unprocessable Entity` | Validation error. |
| `429 Too Many Requests` | Rate limit exceeded. |

**Response Body (`UrlResponse`):**
```json
{
  "id": "uuid",
  "short_code": "string",
  "short_url": "http://localhost:8000/{short_code}",
  "original_url": "string",
  "is_active": true,
  "click_count": 0,
  "expires_at": null,
  "created_at": "2026-07-22T00:00:00Z"
}
```

---

### `GET /api/v1/urls`

List the authenticated user's URLs with search, sort, and pagination.

**Query Parameters:**
| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | string | `null` | Search filter (matches `original_url` or `short_code`, case-insensitive) |
| `sort_by` | string | `created_at` | Sort field: `created_at`, `click_count`, or `short_code` |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `page` | int | `1` | Page number (≥ 1) |
| `page_size` | int | `20` | Items per page (1–100) |

**Responses:**
| Status | Description |
|---|---|
| `200 OK` | Returns `list[UrlResponse]`. |
| `400 Bad Request` | Invalid `sort_by` field. |

---

### `PATCH /api/v1/urls/{url_id}`

Update a URL's properties. Only the owner can update.

**Path Parameters:**
- `url_id` (UUID) — The URL's unique identifier.

**Request Body (all fields optional):**
```json
{
  "original_url": "string (valid HTTP/HTTPS URL)",
  "is_active": false,
  "expires_at": "datetime (ISO 8601)"
}
```

**Responses:**
| Status | Description |
|---|---|
| `200 OK` | Returns updated `UrlResponse`. |
| `403 Forbidden` | Authenticated user does not own this URL. |
| `404 Not Found` | URL does not exist. |

**Side Effects:** Invalidates the Redis cache key `url:{short_code}` after update.

---

### `DELETE /api/v1/urls/{url_id}`

Permanently delete a URL. Only the owner can delete.

**Responses:**
| Status | Description |
|---|---|
| `204 No Content` | Successfully deleted. |
| `403 Forbidden` | Authenticated user does not own this URL. |
| `404 Not Found` | URL does not exist. |

**Side Effects:** Invalidates the Redis cache key `url:{short_code}` after deletion.

---

## Redirect (`app/api/redirect.py`)

### `GET /{short_code}`

Redirect to the original URL. This is the public-facing endpoint — **no authentication required**.

**Responses:**
| Status | Description |
|---|---|
| `302 Found` | Redirects to the original URL via `Location` header. |
| `404 Not Found` | Short code does not exist. |
| `410 Gone` | URL has been deactivated or has expired. |

**Side Effects:**
- Buffers click data in Redis (INCR counter + RPUSH event details) — no synchronous DB writes.
- On first access: caches URL data in Redis with 300s TTL (includes `expires_at`).
- On subsequent access: serves from Redis cache (skips DB SELECT).
- Unknown short codes are cached for 60s (`__miss__` sentinel) to prevent DB stampedes.
- A background flush worker batch-writes buffered clicks to Postgres every 10 seconds.

---

## Analytics (`app/api/analytics.py`)

Prefix: `/api/v1/urls`

### `GET /api/v1/urls/{url_id}/analytics`

Get click analytics for a specific URL. **Only the URL owner can access.**

**Responses:**
| Status | Description |
|---|---|
| `200 OK` | Returns `AnalyticsSummary`. |
| `404 Not Found` | URL not found or not owned by the authenticated user. |

**Response Body (`AnalyticsSummary`):**
```json
{
  "total_clicks": 42,
  "daily_clicks": [
    { "date": "2026-07-25", "clicks": 20 },
    { "date": "2026-07-26", "clicks": 22 }
  ],
  "top_browsers": { "Chrome 91": 30, "Safari 14": 12 },
  "top_devices": { "desktop": 35, "mobile": 7 },
  "top_referrers": { "https://twitter.com": 15, "unknown": 27 }
}
```

---

## Health Checks (`app/api/health.py`)

### `GET /health`

Liveness probe. Returns `200` unconditionally.

```json
{ "status": "ok" }
```

### `GET /ready`

Readiness probe. Checks PostgreSQL and Redis connectivity.

**Responses:**
| Status | Description |
|---|---|
| `200 OK` | All checks passed. `{"ready": true, "checks": {"database": true, "redis": true}}` |
| `503 Service Unavailable` | One or more checks failed. Includes `errors` object with failure details. |

---

## Metrics

### `GET /metrics`

Prometheus-compatible metrics endpoint. Exposed automatically by `prometheus-fastapi-instrumentator`.

Includes:
- HTTP request count, latency histograms (by method, path, status)
- Custom counters: `linkforge_cache_hits_total`, `linkforge_cache_misses_total`, `linkforge_clicks_buffered_total`, `linkforge_clicks_flushed_total`, `linkforge_flush_cycles_total`, `linkforge_flush_errors_total`
- Histogram: `linkforge_redirect_duration_seconds`
