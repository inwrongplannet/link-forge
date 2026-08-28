# Observability

Link Forge implements observability through structured logging, Prometheus metrics, Grafana dashboards, and health check endpoints.

---

## Structured Logging

### Configuration

Logging is configured in `app/utils/logging.py` and initialized at import time in `app/main.py` via `configure_logging()`.

### JSON Format

All log output uses a custom `JsonFormatter` that emits structured JSON to `stdout`:

```json
{
  "level": "INFO",
  "message": "Redirect cache miss for code abc1234",
  "logger": "linkforge",
  "time": "2026-07-27T10:30:00",
  "exception": "Traceback (most recent call last):..."
}
```

The `exception` field is only present when the log record includes exception info.

### Logger Hierarchy

| Logger | Purpose |
|---|---|
| `linkforge` | Application-level logger (created in `main.py`) |
| `uvicorn` | ASGI server logs |
| `uvicorn.access` | HTTP request access logs |
| `uvicorn.error` | Server error logs |

All uvicorn loggers are reconfigured to use the JSON formatter with `propagate=False` to prevent duplicate output.

---

## Prometheus Metrics

### Auto-Instrumentation

The `prometheus-fastapi-instrumentator` library automatically tracks:

- **`http_requests_total`** — Total HTTP requests (by method, handler, status)
- **`http_request_duration_seconds`** — Request latency histogram (by method, handler)
- **`http_request_size_bytes`** — Request body size
- **`http_response_size_bytes`** — Response body size
- **`http_requests_in_progress`** — Gauge of concurrent requests

Metrics are exposed at **`GET /metrics`** in Prometheus exposition format.

### Custom Metrics

Defined in `app/cache/metrics.py`:

| Metric | Type | Description |
|---|---|---|
| `linkforge_cache_hits_total` | Counter | Redirect served from Redis cache |
| `linkforge_cache_misses_total` | Counter | Redirect required PostgreSQL lookup |

These allow calculating the **cache hit ratio**:
```
cache_hit_ratio = linkforge_cache_hits_total / (linkforge_cache_hits_total + linkforge_cache_misses_total)
```

---

## Prometheus Configuration

The `prometheus.yml` at the project root configures Prometheus to scrape the app:

```yaml
scrape_configs:
  - job_name: "linkforge"
    scrape_interval: 5s
    static_configs:
      - targets: ["web:8000"]
```

- **Target:** The `web` Docker Compose service on port 8000
- **Scrape interval:** Every 5 seconds
- **Access:** Prometheus UI at `http://localhost:9090` (Docker Compose)

---

## Grafana

Grafana is included in the Docker Compose stack for visualization:

- **Access:** `http://localhost:3001`
- **Default credentials:** `admin` / `admin`
- **Data source:** Add Prometheus at `http://prometheus:9090`

### Suggested Dashboard Panels

| Panel | PromQL Query |
|---|---|
| Request Rate | `rate(http_requests_total[5m])` |
| p95 Latency | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` |
| Error Rate | `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])` |
| Cache Hit Ratio | `rate(linkforge_cache_hits_total[5m]) / (rate(linkforge_cache_hits_total[5m]) + rate(linkforge_cache_misses_total[5m]))` |
| Active Requests | `http_requests_in_progress` |
| Redirect Latency | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{handler="/[short_code]"}[5m]))` |

---

## Health Check Endpoints

Defined in `app/api/health.py`.

### `GET /health` — Liveness Probe

Always returns `200 OK`:
```json
{ "status": "ok" }
```

Use for Kubernetes `livenessProbe` or Docker `HEALTHCHECK` to detect if the process is running.

### `GET /ready` — Readiness Probe

Performs active checks against dependencies:

| Check | Method |
|---|---|
| **Database** | `SELECT 1` via SQLAlchemy session |
| **Redis** | `redis_client.ping()` |

**Healthy response (200):**
```json
{
  "ready": true,
  "checks": { "database": true, "redis": true }
}
```

**Unhealthy response (503):**
```json
{
  "ready": false,
  "checks": { "database": true, "redis": false },
  "errors": { "redis": "Connection refused" }
}
```

Use for Kubernetes `readinessProbe` or load balancer health checks to prevent routing traffic to an unready instance.

---

## Error Tracking

Global exception handlers in `app/middleware/error_handlers.py` log errors before returning structured JSON responses:

- **Database errors** (`SQLAlchemyError`) — Logged at `ERROR` level with the exception message
- **Unhandled errors** (`Exception`) — Logged at `ERROR` level with full traceback (`exc_info=True`)
- **Validation errors** — Not logged (client errors, returned as 422)

The top-level catch-all in `app/main.py` additionally logs unhandled exceptions with request method and path:
```python
logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
```

---

## Docker Compose Observability Stack

The `docker-compose.yml` includes the full observability stack:

| Service | Port | Purpose |
|---|---|---|
| `web` | 8080 (→8000) | Application (exposes `/metrics`) |
| `prometheus` | 9090 | Metrics collection & querying |
| `grafana` | 3001 (→3000) | Metrics visualization & dashboards |
