# Link Forge — Load Test Root-Cause Analysis & Improvement Strategies

**Source:** `loadtests/RESULTS.md` on branch `remobing-global-cap` (github.com/inwrongplannet/link-forge)
**Performance goal:** 1,000 RPS, p95 < 100 ms, < 1 % error rate
**Best result achieved:** ~121 RPS (100 % failures), redirect p50 of 9.3 s in k6 — roughly two orders of magnitude off target on every axis.

---

## 1. Executive Summary

The load test results are not caused by one bug. They are the compound effect of **five stacked bottlenecks**, each of which caps throughput below the previous one:

1. **A single Uvicorn worker process** — the whole app runs on one Python process (one core, GIL-bound).
2. **Every route is a synchronous `def`** — requests are serviced by AnyIO's worker threadpool (default **40 threads**), so 500 concurrent users queue behind 40 slots.
3. **bcrypt at 12 rounds runs inline on register *and* login** (~250–350 ms of pure CPU each) — 500 Locust users all registering + logging in at spawn saturates the single core for minutes.
4. **A default-sized SQLAlchemy pool (5 + 10 overflow = 15 connections)** — threads queue 30 s for a connection, then raise, which surfaces as the 500 "Internal Server Error" storm.
5. **The redirect "cache hit" path still performs two synchronous Postgres writes + COMMIT per request** — and both test scripts hammer a *single* short code, so all 500 VUs serialize on one row lock. This alone explains the k6 result of ~50 RPS at p50 ≈ 9.3 s.

On top of that, most of the headline error percentages are **test-design artifacts, not server errors**: users whose login failed spent the whole run firing token-less requests (the 45,000+ 401s), the IP-keyed global rate limit put every load-test user in one shared 60/min bucket (the 429 storms), and Run 8's 100 % "Connection refused" simply means the server was not running.

The good news: the fixes are well understood, cheap, and mostly independent. Section 5 lays them out in phases, starting with changes that should get redirects from ~50 RPS to >1,000 RPS.

---

## 2. What the Results Actually Show (Run-by-Run Diagnosis)

| Run | Headline symptom | Actual diagnosis |
|---|---|---|
| **Locust 1 & 3** (Aug 6) | 96–98 % errors, login p50 of 2–5 *minutes* | Auth collapse. 500 users × (register + login) = ~1,000 bcrypt operations ≈ 4–6 min of CPU on one core. Requests queue in the 40-thread pool; DB connections time out (→ the 500s); users without tokens spam `/api/v1/urls` (→ the 11,508 / 3,735 401s). |
| **Locust 2** (Aug 6) | 5.7 % errors, p95 = 34 ms, but only 3 RPS | The server is fine at trivial load. The 63 × 429 show the **global 60/min-per-IP rate limit** capping URL creation — the whole test shares one IP, so throughput can't rise. |
| **Locust 4** (Aug 27) | 79 % errors, mixed 401/500/429 | Same auth collapse + rate-limit cap, shorter run. |
| **Locust 5** (Aug 27) | 34 % errors; 18,010 redirects at 0 % errors but p95 = 370 ms | Best "real" data point: cached redirects work but latency climbs with load because every redirect still writes to Postgres. 5,615 × 429 = the shared IP bucket exhausted again; 3,795 × 401 = tokenless users. |
| **Locust 6** (Aug 28, after rate limit removed) | 87 % errors, 45,266 × 401, 115 dropped connections | Removing the limiter uncorked more traffic into the same bottlenecks. Login p50 = 226 s (87 % failed) → almost no users got tokens → 401 firehose. `RemoteDisconnected` = the overloaded server shedding connections. |
| **Locust 7** (Aug 28) | 27 % errors, everything p50 ≈ 2.2 s with 60 s maxima | Server already saturated/degraded when the run started (short 75 s run, all four endpoints slow simultaneously → queueing at the threadpool, not endpoint-specific cost). |
| **Locust 8** (Aug 28) | 100 % `ConnectionRefusedError(111)` in ~4 ms | **The app was not listening on :8080.** The container was down or restarting. This run contains zero performance information and should be struck from the results; it also shows no pre-run health gate exists. |
| **k6 runs 1–4** | 0 % errors but ~50 RPS and p50 ≈ 9.3–9.5 s | The smoking gun for the hot path. All 500 VUs request **one short code** (`SHORT_CODE=cEhtRPZ`). Every request — even on Redis cache hit — executes `UPDATE urls SET click_count = click_count + 1` on the *same row*, plus an INSERT into `clicks`, plus COMMIT. Postgres serializes the row-level lock, so the whole fleet processes ~50 tx/s. Little's law confirms it: 500 VUs × ~9.5 s ≈ 50 RPS. Redis is not the bottleneck; the synchronous write-per-redirect is. |

**Key reframing:** the 95–100 % "error rates" in the summary table are dominated by 401s and 429s that are *downstream consequences* of (a) auth collapsing at spawn time and (b) an IP-keyed rate limit meeting a single-IP load generator. The server's true failures are the 500s (pool exhaustion), the multi-minute latencies (threadpool + CPU saturation), and the dropped connections.

---

## 3. Root Causes (Ranked by Impact)

### RC-1 — Synchronous DB writes on the redirect hot path, serialized on one row ✅ RESOLVED

> **Status:** Fixed via Strategy A (Redis counters + batch flush). See `app/cache/click_buffer.py` and `app/cache/flush_worker.py`.

`app/api/redirect.py:28-31` — even on a cache hit, every redirect does:

```python
db.execute(update(Url).where(Url.id == data["id"]).values(click_count=Url.click_count + 1))
record_click(db, data["id"], request)   # INSERT into clicks
db.commit()
```

- Two writes + a commit per redirect means the "Redis cache" only removes the *read*, not the expensive part.
- Both `loadtests/redirect_test.js` (fixed `SHORT_CODE`) and `loadtests/locustfile.py:41` (`self.short_codes[0]`) target one code → **all transactions contend for the same row lock** and execute one-at-a-time.
- Ceiling ≈ 1 / (lock wait + commit latency) ≈ 50 RPS, exactly what k6 measured, with 9–11 s of queueing per request.

### RC-2 — Single-process, sync-only concurrency model
- `Dockerfile:28` / `docker-compose.yml:19`: `uvicorn app.main:app` with **no `--workers`** → one process, one core.
- Every endpoint is `def`, not `async def` (`app/api/*.py`), so each request occupies one of AnyIO's **40 default threadpool threads** for its entire duration. 500 concurrent users → 460 requests waiting in queue at any moment. This converts *any* slowness into 60–300 s queue times, which is what the login/register percentiles show.
- The Redis client (`app/cache/redis_client.py`) is the blocking `redis` library — consistent with sync routes, but it pins the app to this model.

### RC-3 — bcrypt(12) inline on the request path
- `app/auth/password.py:4`: `bcrypt.gensalt(rounds=12)` ≈ 250–350 ms of CPU per hash/verify.
- `loadtests/locustfile.py:17-27` makes **every one of 500 users register and log in during ramp-up** → ~1,000 bcrypt ops ≈ 4–6 minutes of CPU handed to a single-core process, all while each operation also **holds a checked-out DB connection** (session transaction opened by the preceding SELECT stays open through the hash until `commit()`).

### RC-4 — Default SQLAlchemy pool (15 connections) with 40 threads competing
- `app/database/session.py:13`: `create_engine(DATABASE_URL, future=True, pool_pre_ping=True)` — no `pool_size`/`max_overflow`/`pool_timeout`. Defaults: 5 + 10 overflow, 30 s checkout timeout.
- Under load, threads wait 30 s for a connection then raise `TimeoutError` → caught by the `SQLAlchemyError` handler (`app/middleware/error_handlers.py:27`) → the **500 "database_error"** responses concentrated on register/login (the endpoints that hold connections longest, per RC-3).

### RC-5 — IP-keyed global rate limit vs. a single-IP load generator
- `app/middleware/rate_limit.py:5`: `Limiter(key_func=get_remote_address, default_limits=["60/minute"])`. All Locust traffic arrives from one IP → the entire 500-user fleet shares **one 60/min bucket** for URL creation → thousands of 429s (Runs 2, 4, 5).
- The branch's response (commit `e809b63`) was to **delete the limiter wiring from `app/main.py` entirely** — which fixed the 429s but removed all protection and left dead config behind. The correct fix is a smarter key and test-time configuration (see S-5).
- Latent bug for later: slowapi's default in-memory storage is **per-process**, so the moment you add `--workers N`, limits become N× too generous and inconsistent. It needs a Redis storage backend.

### RC-6 — Test design measuring the test, not the server
- 500 users register/login at spawn (thundering herd that no real system sees).
- Users who fail login **keep running anyway**, generating 401s that pollute every error metric (`locustfile.py` never aborts on auth failure — 45,263 of Run 6's 45,826 "failures" are this).
- One short code shared by all VUs (unrealistic hot-key, RC-1 amplifier).
- Locust's default `HttpUser` (python-requests) at 500 users is itself CPU-heavy, and load generator + app + Postgres + Redis all ran on the same machine (`localhost:8080`), so the generator steals CPU from the system under test.
- Run 8 executed against a dead server; nothing gates a run on `/health`.
- The "Performance Tuning Log" section in RESULTS.md is empty — runs aren't annotated with the code/config they tested, so run-over-run comparisons (e.g. Run 5 vs Run 6) are guesswork.

### RC-7 — Secondary contributors
- **Per-request user lookup:** `get_current_user` does `db.get(User, claims["sub"])` on every authenticated call (`app/auth/dependencies.py:25`) — an extra DB round-trip per request that adds pool pressure.
- **User-agent parsing on the hot path:** `user_agents.parse()` per click (`app/analytics/parser.py:4`) is regex-heavy CPU work inside the redirect transaction.
- **No server tuning at all:** no `--limit-concurrency`, no keep-alive/backlog tuning, no uvloop/httptools; Postgres is a stock `postgres:15` container; no container restart policy (Run 8) and no compose healthcheck on `web`.
- **Correctness bug found along the way:** the cache-hit path never checks `expires_at` (it isn't stored in the cached JSON, `app/api/redirect.py:42-46`), so an expired link keeps redirecting for up to 300 s of TTL. Not a perf issue, but fix it while touching this code.

---

## 4. Improvement Strategies

Multiple strategies per problem, grouped by layer. Each item notes the root cause it addresses.

### S-1. Fix the redirect hot path (RC-1) — the single biggest win

**Strategy A — Count clicks in Redis, flush to Postgres in batches (recommended).** ✅ IMPLEMENTED
On each redirect: `INCR clicks:{short_code}` (and optionally `RPUSH`/`XADD` the click-event details to a Redis list/stream). A background task (asyncio task, or a separate worker container) wakes every 5–10 s, drains the counters/events, and applies them in bulk: one `UPDATE urls SET click_count = click_count + N` per code and one `INSERT ... VALUES (...), (...), ...` (or `COPY`) for click rows. The redirect response then touches **only Redis** on a cache hit → sub-millisecond hot path, no row-lock convoy, and writes to Postgres shrink from 2-per-request to 2-per-flush-interval.

> **Implementation:** `app/cache/click_buffer.py` (buffer_click + drain_click_buffer), `app/cache/flush_worker.py` (flush_once + run_flush_worker). Also implemented: `expires_at` in cache payload, negative caching with `__miss__` sentinel.

**Strategy B — Fire-and-forget with `BackgroundTasks` (minimal change).**
Return the 302 first; do the count update and click insert in a FastAPI `BackgroundTasks` after the response. This removes write latency from the user-facing path with a ~10-line diff, but keeps the same total DB write volume and the hot-row lock, so it helps latency, not throughput ceiling. Good as an interim step, not the destination.

**Strategy C — Message queue for analytics events (long-term).**
Publish click events to a queue (Redis Streams now; Kafka/RabbitMQ if this grows) consumed by a dedicated analytics writer. Decouples redirect availability from analytics durability entirely and later lets you swap the analytics store (e.g. ClickHouse/TimescaleDB for the `clicks` table, which will dwarf everything else in row count).

**Strategy D — If you keep synchronous counting, avoid the single-row convoy.**
Sharded counters (`click_count_shard_0..15`, pick one at random, sum on read) or `synchronous_commit = off` for the clicks transaction. These are known Postgres patterns, but honestly A/C make them unnecessary here.

Also while in this file: store `expires_at` in the cached payload and check it on cache hits; add short-TTL **negative caching** (`url:{code} = "__miss__"`, 30–60 s) so unknown codes don't stampede Postgres.

### S-2. Fix the concurrency model (RC-2)

**Strategy A — Go async on the hot paths (recommended).**
Convert `redirect.py` (and ideally `urls.py`/`auth.py`) to `async def`, using SQLAlchemy's async engine (`create_async_engine` + `AsyncSession`, psycopg3 already supports async) and `redis.asyncio`. Async routes are served by the event loop, not the 40-thread pool, so 500 concurrent waiters become cheap. This is the idiomatic FastAPI shape and removes the queueing cliff entirely.

**Strategy B — Scale processes: run multiple workers.**
`uvicorn app.main:app --workers <2×cores>` (or gunicorn with `-k uvicorn.workers.UvicornWorker`). This multiplies CPU capacity for bcrypt and JSON work and is a one-line compose change. Do this *regardless* of Strategy A. Prerequisites: rate-limiter storage must move to Redis (RC-5 note), and `initialize_database()` should be replaced by an Alembic migration step so N workers don't race `create_all` (the compose file's comment already promises migrations it never runs — `docker-compose.yml:17`).

**Strategy C — If staying sync, at least raise the threadpool.**
`anyio.to_thread.current_default_thread_limiter().total_tokens = 100+` (or via Starlette config). Strictly worse than A/B but documents the real constraint.

**Strategy D — Server tuning.**
Add `--limit-concurrency` (shed load with fast 503s instead of 300 s queue times), tune `--backlog` and `--timeout-keep-alive`, and install `uvloop`+`httptools` (uvicorn's performance extras) for free event-loop throughput.

### S-3. Fix auth cost (RC-3)

- **Offload hashing off the event loop/threadpool hot path:** with async handlers, run bcrypt in `run_in_threadpool` (or a `ProcessPoolExecutor` to escape the GIL entirely).
- **Don't hold a DB connection during the hash:** in `register`, do the uniqueness SELECT, close/commit the read transaction, *then* hash, then open a short write transaction. (Or hash before touching the DB at all — the unique constraint already guards races, and `url_service.py` shows the retry pattern.)
- **Right-size the work factor:** bcrypt(12) is a defensible production choice, but make rounds configurable via `Settings` and use 4–6 in load-test/dev environments so tests measure the system, not the KDF. Alternatively adopt **argon2id** with parameters tuned to your latency budget.
- **Cache the auth lookup:** cache `get_current_user`'s user-exists check in Redis for ~60 s (or trust the JWT until expiry — it's only 15 min — and drop the per-request `db.get(User, ...)` entirely, `app/auth/dependencies.py:25`). Removes one DB round-trip from every authenticated request.
- **Protect login specifically** with a per-account/per-IP limiter (fail2ban-style), which is the rate limit that actually matters for auth.

### S-4. Fix the database layer (RC-4)

- **Size the pool explicitly:** e.g. `pool_size=20, max_overflow=20, pool_timeout=5, pool_recycle=1800` per worker, keeping `workers × (pool_size+overflow)` under Postgres `max_connections` (default 100 — raise it or add **PgBouncer** in transaction mode if you scale workers).
- **Fail fast:** a 5 s `pool_timeout` turns 30-second hangs into quick 503s the load balancer/test can see honestly.
- **Bulk-write clicks** (comes free with S-1A/C); long-term, partition `clicks` by month and add a composite index `(url_id, clicked_at)` for the analytics queries.
- **Use Alembic in the container startup** (`alembic upgrade head && uvicorn ...`) instead of `create_all` at import of every worker.
- **Enable `pg_stat_statements`** and watch it during runs — it would have shown the `UPDATE urls` hot row immediately.

### S-5. Rate limiting done right (RC-5) — instead of deleting it

- **Re-wire the limiter** with a smarter key: user ID (from the JWT) for authenticated routes, IP only for anonymous ones; **exempt `GET /{short_code}`** or give it a very high dedicated limit — redirects are the product.
- **Move storage to Redis** (`Limiter(storage_uri=settings.redis_url)`) so limits are correct across multiple workers.
- **Make limits environment-driven** (`RATE_LIMIT_PER_MINUTE` already exists in `Settings`) so load tests raise them via env var rather than a code-deleting branch.
- **Return `Retry-After`** (slowapi's `headers_enabled=True` already does) and have load-test clients respect it, so 429s stop counting as "failures."
- Consider a **token-bucket at the edge** (nginx `limit_req`, or Traefik middleware) for coarse abuse protection independent of app workers.

### S-6. Fix the load tests so they measure the server (RC-6)

- **Seed accounts and tokens up front** (extend `seed.py` to create N users + M URLs; distribute tokens to VUs via CSV/env). `on_start` should at most log in — never register — and must **`raise StopUser`/abort when auth fails** so a broken user doesn't spend 8 minutes generating 401 noise.
- **Spread traffic across many short codes** with a realistic skew (Zipf: some hot, long tail warm) instead of one code — both in `locustfile.py` and `redirect_test.js` (pass a code list, pick randomly).
- **Split scenarios:** (1) redirect-only read test, (2) URL-creation write test, (3) auth test, (4) combined realistic mix (e.g. 95 % redirects / 4 % creates / 1 % auth — a URL shortener is overwhelmingly read-heavy). One number per scenario beats one blended number that hides everything.
- **Use `FastHttpUser`** in Locust (5–10× less generator CPU) or standardize on k6; run the generator on a different machine (or a CPU-pinned container) than the app+DB, and **record host CPU/memory during runs** — at `localhost`, generator and server compete for the same cores.
- **Gate every run on health:** script the run to check `/ready` first and abort otherwise (kills Run-8-style garbage data), and fail loudly mid-run if error rate exceeds a threshold.
- **Fill in the Performance Tuning Log:** every row in RESULTS.md should carry the git SHA, worker count, pool size, and rate-limit config it tested. `run_k6_tests.py` already automates result capture — extend it to also stamp `git rev-parse HEAD` and the relevant env vars.
- **Ramp gradually and find the knee:** step load (50 → 100 → 200 → 400 → 800 users) with a hold at each step to identify where p95 crosses 100 ms, rather than slamming 500 users instantly.

### S-7. Infrastructure & operations

- **docker-compose:** add a `healthcheck` on `web` (curl `/ready`), `restart: unless-stopped` (mitigates Run 8), CPU/memory limits per service so Postgres and the app don't starve each other, and actually run migrations in `command`.
- **Horizontal scale path:** compose `deploy.replicas` (or multiple `web` services) behind an **nginx/Traefik** reverse proxy; this also gives you access logs, keep-alive management, and edge rate limiting.
- **Postgres tuning:** `shared_buffers`, `effective_cache_size`, `max_connections`; `synchronous_commit = off` is acceptable for the clicks/analytics write path if you adopt batched writes.
- **Observability you already half-have:** Prometheus + Grafana containers exist and `cache_hits`/`cache_misses` counters are wired (`app/cache/metrics.py`) — build one dashboard with p50/p95/p99 per endpoint (the Instrumentator exposes these), DB pool checked-out/waiting gauges (`sqlalchemy.pool` events), Redis hit ratio, and container CPU (cAdvisor/node-exporter). Every future RESULTS.md row should link a Grafana snapshot.

### S-8. Longer-term architecture (once the above is done)

- **Pre-generated key service:** batch-generate short codes offline into a Redis pool and `SPOP` one per create — removes the IntegrityError retry loop (`app/services/url_service.py:17-29`) and its collision risk at scale.
- **Cache warming + longer TTLs with explicit invalidation:** you already `DELETE` on update/delete, so the 300 s TTL can grow substantially; consider `SETEX` on create so first-hit misses disappear.
- **Read replicas / regional caches or a CDN** in front of `GET /{short_code}` (redirects are ideal CDN/edge-worker material).
- **Analytics store split:** move `clicks` into a columnar/append-optimized store (ClickHouse, Timescale) fed by the S-1C queue; Postgres keeps `users`/`urls`.

---

## 5. Recommended Phased Plan

| Phase | Changes | Effort | Expected outcome |
|---|---|---|---|
| **0. Make results trustworthy** | S-6 (seed users, abort on auth failure, many short codes, health gate, log SHA/config per run), re-run baseline | ~½ day | A believable baseline; error % reflects the server, not the test |
| **1. Capacity quick wins** | S-2B (`--workers`), S-4 pool sizing + fast timeout, S-3 test-time bcrypt rounds via env, S-7 compose healthcheck/restart | ~½ day | Auth stops collapsing; 500s disappear; multi-minute latencies drop to seconds |
| **2. Hot-path redesign** | S-1A (Redis counters + batch flush), negative caching, `expires_at` in cache | ✅ DONE | Redirects go from ~50 RPS to 1,000+ RPS with p95 well under 100 ms (Redis-only hot path) |
| **3. Async + real rate limiting** | S-2A (async routes/engine/redis), S-5 (per-user limits, Redis storage, exempt redirects) | 2–3 days | Headroom under 500+ concurrent users; protection restored without 429 noise |
| **4. Scale-out & observability** | S-7 proxy + replicas + dashboards, S-4 PgBouncer if needed | 2–3 days | Documented capacity curve; regressions visible per run |
| **5. Architecture (as growth demands)** | S-8 items | ongoing | CDN-class redirect latency; analytics at scale |

**Re-test protocol after each phase:** same seeded dataset, same scenario files, stepped ramp to the knee, one RESULTS.md row per scenario with git SHA + config + Grafana snapshot. Only change one layer per test cycle so the Performance Tuning Log finally tells a causal story.

---

## 6. Root Cause ↔ Evidence ↔ Strategy Map

| # | Root cause | Key evidence | Strategies |
|---|---|---|---|
| RC-1 | Sync DB writes per redirect + single hot row | k6: 50 RPS, p50 9.3 s, 0 % errors; `redirect.py:28-31` | ✅ S-1A implemented (Redis counters + batch flush, negative caching, expires_at in cache) |
| RC-2 | 1 worker, sync routes, 40-thread ceiling | 60–390 s latencies across all endpoints; `Dockerfile:28` | S-2 (A + B), S-2D |
| RC-3 | bcrypt(12) inline at spawn stampede | login p50 61–303 s, register p50 up to 152 s | S-3, S-6 seeded tokens |
| RC-4 | Default 15-conn pool, 30 s checkout timeout | 500 "database_error" clusters on auth routes; `session.py:13` | S-4 |
| RC-5 | IP-keyed 60/min global limit; then deleted | 5,615 × 429 in Run 5; commit `e809b63` | S-5 |
| RC-6 | Test measures its own failure modes | 45k × 401 in Run 6; Run 8 100 % conn-refused; single short code | S-6, S-7 healthcheck |
| RC-7 | Per-request user lookup, UA parsing, no server/PG tuning, no restart policy | `dependencies.py:25`, `parser.py:4`, compose file | S-3 cache, S-1 moves parsing off-path, S-7 |
