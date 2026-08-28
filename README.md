# Link Forge

Link Forge is a robust, production-ready URL shortener API built with FastAPI. It features JWT-based authentication, Redis caching, rate limiting, and PostgreSQL for persistent storage.

## Features

- **URL Shortening:** Generate shortened URLs for any valid original URL.
- **Analytics:** Track click counts, referrers, and device types.
- **Authentication:** Secure endpoints using JWT access and refresh tokens.
- **High Performance:** Uses Redis for Cache-Aside to serve redirects blisteringly fast without hitting the database.
- **Rate Limiting:** Protects the API from abuse and scraping using SlowAPI.
- **Containerized:** Fully reproducible Docker environment for easy deployments.
- **Automated Testing:** Comprehensive unit and integration testing suite utilizing nested transaction rollbacks.

---

## 🚀 Setup Instructions

### 1. Running Locally (Development)

**Prerequisites:**
- Python 3.12+
- PostgreSQL 15+
- Redis 7+

**Steps:**

1. **Clone the repository**
   ```bash
   git clone https://github.com/Abhishek-M-29/link-forge.git
   cd link-forge
   ```

2. **Set up a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**
   Ensure your local `.env` file is properly configured with your PostgreSQL and Redis credentials.
   ```env
   DATABASE_URL=postgresql+psycopg://postgres:password123@localhost:5432/link_forge
   REDIS_URL=redis://localhost:6379/0
   JWT_SECRET=your_super_secret_key
   ```

5. **Start the API server**
   ```bash
   # The database schema will be automatically initialized on startup
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

6. **Run Tests**
   ```bash
   PYTHONPATH=. pytest tests/ -s
   ```

---

### 2. Running with Docker (Recommended)

The easiest way to get the application running is via Docker Compose, which spins up the web server, PostgreSQL, and Redis in isolated containers.

**Prerequisites:**
- Docker & Docker Compose

**Steps:**

1. **Build and start the containers**
   ```bash
   docker compose up --build -d
   ```
   *The API will be available at `http://localhost:8080`.*

2. **Run tests inside Docker**
   ```bash
   docker compose exec web pytest tests/ -s
   ```

3. **Shut down the environment**
   ```bash
   docker compose down -v
   ```

---

## Load Testing

Start the Docker environment before running either load test:

```bash
docker compose up --build -d
```

### k6 Redirect Test

Install [k6](https://k6.io/docs/get-started/installation/) and create a valid test URL. `seed.py` prints the generated short code:

```bash
pip install -r requirements.txt
SHORT_CODE=$(python seed.py | tail -1)
k6 run -e SHORT_CODE="$SHORT_CODE" loadtests/redirect_test.js
```

The k6 script sends requests to `http://localhost:8080/<short_code>` and requires `SHORT_CODE` to be set.

### Locust Test

Install Locust and run the test against the Docker API:

```bash
pip install locust
locust -f loadtests/locustfile.py --host http://localhost:8080
```

Then open `http://localhost:8089` to configure and start the Locust run.

---

## 📡 API Overview

Once the application is running, you can access the interactive API documentation (Swagger UI) at:
- `http://localhost:8000/docs` (Local)
- `http://localhost:8080/docs` (Docker)

### Core Endpoints:
- `POST /api/v1/auth/register` - Register a new user
- `POST /api/v1/auth/login` - Authenticate and receive JWT tokens
- `POST /api/v1/urls` - Create a new shortened URL (Requires Auth)
- `GET /{short_code}` - Redirect to the original URL
- `GET /api/v1/analytics/{url_id}` - View URL statistics (Requires Auth)

### Monitoring & Operations:
- `GET /health` - Liveness probe
- `GET /ready` - Readiness probe (Database & Redis connection check)
- `GET /metrics` - Prometheus metrics (Request rates, latencies, Cache hit ratio)

---

## 🛠 Accessing Integrated Components

When running the application via Docker Compose, all integrated components are exposed to your local machine for easy access and monitoring:

- **FastAPI Application (API & Docs):** [http://localhost:8080](http://localhost:8080) / [http://localhost:8080/docs](http://localhost:8080/docs)
- **PostgreSQL Database:** `localhost:5433` (User: `link_forge_user`, Password: `password123`, DB: `link_forge`)
- **Redis Cache:** `localhost:6380`
- **Prometheus (Metrics Scraper):** [http://localhost:9090](http://localhost:9090)
- **Grafana (Dashboards):** [http://localhost:3001](http://localhost:3001) (Default login: `admin` / `admin`)

*Note: To view metrics in Grafana, add the Prometheus data source at `http://prometheus:9090` (using Docker's internal network) and create your dashboards.*
