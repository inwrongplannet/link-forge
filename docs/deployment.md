# Deployment

This document covers how to deploy and run Link Forge in various environments.

---

## Local Development

### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Redis 7+

### Setup

```bash
# Clone and enter the project
git clone https://github.com/Abhishek-M-29/link-forge.git
cd link-forge

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
# Edit .env with your credentials
```

### Required Environment Variables

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/link_forge
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret-key-here
```

### Start the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

### Run Tests

```bash
PYTHONPATH=. pytest tests/ -s
```

---

## Docker Compose (Recommended)

Docker Compose starts the full stack: application, PostgreSQL, Redis, Prometheus, and Grafana.

### Start

```bash
docker compose up --build -d
```

### Service Ports

| Service | URL | Purpose |
|---|---|---|
| API | `http://localhost:8080` | Application |
| API Docs | `http://localhost:8080/docs` | Swagger UI |
| PostgreSQL | `localhost:5433` | Database (external access) |
| Redis | `localhost:6380` | Cache (external access) |
| Prometheus | `http://localhost:9090` | Metrics |
| Grafana | `http://localhost:3001` | Dashboards |

### Run Tests in Docker

```bash
docker compose exec web pytest tests/ -s
```

### Stop and Clean Up

```bash
# Stop containers (keep data)
docker compose down

# Stop and delete all data volumes
docker compose down -v
```

---

## Dockerfile

The production `Dockerfile` uses `python:3.12-slim` and:

1. Sets `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`
2. Installs system dependencies: `gcc`, `libpq-dev`, `curl`
3. Installs Python dependencies from `requirements.txt`
4. Copies the project files
5. Exposes port 8000
6. Runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Build Standalone

```bash
docker build -t link-forge .
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+psycopg://user:pass@host:5432/link_forge \
  -e REDIS_URL=redis://host:6379/0 \
  -e JWT_SECRET_KEY=your-secret \
  link-forge
```

---

## CI/CD — GitHub Actions

The CI pipeline is defined in `.github/workflows/ci.yml` and runs on every push/PR to `main`.

### What it does:

1. **Services:** Starts PostgreSQL 15 and Redis 7 as service containers
2. **Python:** Sets up Python 3.12
3. **Dependencies:** Installs from `requirements.txt`
4. **Tests:** Runs `pytest tests/ -s` with CI-specific environment variables

### CI Environment Variables:

```yaml
DATABASE_URL: postgresql+psycopg://link_forge_user:password123@localhost:5432/link_forge
REDIS_URL: redis://localhost:6379/0
JWT_SECRET: ci-super-secret-key
PYTHONPATH: .
```

---

## Database Seeding

The `seed.py` script creates a test user and URL, useful for load testing:

```bash
python seed.py
```

This registers a random user, logs in, creates a URL, and prints the short code. The script targets `http://localhost:8080` (Docker Compose port).

---

## Load Testing

### Locust

```bash
locust -f loadtests/locustfile.py --host http://localhost:8080
```

The Locust test simulates users with a 9:1 read:write ratio (9 redirects per 1 URL creation). Each virtual user registers a unique account and authenticates before starting.

### k6

```bash
# First, seed the database
python seed.py

# Edit redirect_test.js to use the real short code, then:
k6 run loadtests/redirect_test.js
```

The k6 test ramps to 500 virtual users with thresholds:
- p95 latency < 100ms
- Error rate < 1%

### Performance Goals

| Metric | Target |
|---|---|
| Throughput | ≥ 1,000 RPS |
| p95 Latency | < 100ms |
| Error Rate | < 1% |

Results are tracked in `loadtests/RESULTS.md`.

---

## Production Considerations

### Security

- **Change `JWT_SECRET_KEY`** to a strong, unique value (use `openssl rand -hex 32`)
- **Change database passwords** from defaults
- **Use HTTPS** in production (set `BASE_URL` accordingly)
- **Remove or restrict** the `/metrics` endpoint behind a firewall

### Scaling

- **Horizontal scaling:** The app is stateless — run multiple instances behind a load balancer
- **Database connection pooling:** Consider PgBouncer for high-concurrency deployments
- **Redis:** Use Redis Cluster or Sentinel for high availability

### Monitoring

- Configure Prometheus alerting rules for error rate and latency spikes
- Set up Grafana alerts for cache hit ratio drops
- Forward JSON logs to a centralized log aggregation system (e.g., ELK, Loki)
