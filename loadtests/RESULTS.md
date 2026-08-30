# Load Testing Results

This document tracks the performance metrics achieved during our load testing iterations.
It serves as evidence of meeting our performance goals (1000 RPS, p95 < 100ms, <1% error rate).

> **Last Updated**: 2026-08-30 10:21:00

---

## 1. Summary Table (All Runs)

| # | Date & Time | Tool | Users | Duration | Total Reqs | Total Fails | Agg RPS | Agg Fail/s | p50 | p95 | p99 | Max | Error Rate | Avg Content Len |
| :--- | :--- | :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2026-08-06-09h13 | Locust | 500 | 7 minutes and 54 seconds | 12,326 | 12,137 | 26.0 | 25.6 | 9ms | 68.0s | 307.0s | 459.4s | 98.47% | 34.4B |
| 2 | 2026-08-06-09h26 | Locust | 500 | 6 minutes and 14 seconds | 1,114 | 63 | 3.0 | 0.2 | 26ms | 34ms | 40ms | 10.3s | 5.66% | 16.6B |
| 3 | 2026-08-06-09h33 | Locust | 500 | 4 minutes and 45 seconds | 4,255 | 4,083 | 14.9 | 14.3 | 9ms | 126.0s | 247.0s | 277.0s | 95.96% | 38.8B |
| 4 | 2026-08-27-20h17 | Locust | 500 | 2 minutes and 58 seconds | 1,143 | 907 | 6.5 | 5.1 | 12ms | 117.0s | 144.0s | 144.8s | 79.35% | 72.1B |
| 5 | 2026-08-27-20h24 | Locust | 500 | 6 minutes and 54 seconds | 27,690 | 9,455 | 66.9 | 22.8 | 140ms | 400ms | 1.0s | 89.6s | 34.15% | 16.0B |
| 6 | 2026-08-28-17h07 | Locust | 500 | 8 minutes and 55 seconds | 52,624 | 45,826 | 98.3 | 85.6 | 9ms | 820ms | 36.0s | 389.5s | 87.08% | 31.1B |
| 7 | 2026-08-28-19h49 | Locust | 500 | 1 minute and 15 seconds | 373 | 101 | 5.0 | 1.4 | 2.2s | 62.0s | 63.0s | 65.3s | 27.08% | 148.8B |
| 8 | 2026-08-28-20h09 | Locust | 350 | 1 minute and 59 seconds | 14,463 | 14,463 | 121.3 | 121.3 | 4ms | 37ms | 170.0ms | 391.0ms | 100.00% | 0.0B |
| 9 | 2026-08-30-10h21 | k6 | 500 | 2 minutes | 11,289 | 0 | 94.0 | 0.0 | 4.79s | 5.53s | — | 5.88s | 0.00% | — |

---

## 2. k6 Redirect Stress Tests (Redis Cache)

These tests exclusively targeted the `GET /[short_code]` redirect endpoint (served from Redis cache).
All runs used 500 Virtual Users, 30s duration, no rate limiting.

| Run | RPS | p50 | p95 | p99 | Error Rate | Notes |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| Run 1 | 50 | 9314.7ms | 10527.8ms | 11011.8ms | 0.00% | Uncapped Stress Test |
| Run 2 | 50 | 9349.3ms | 10415.5ms | 10881.1ms | 0.00% | Uncapped Stress Test |
| Run 3 | 49 | 9499.0ms | 10546.5ms | 11027.0ms | 0.00% | Uncapped Stress Test |
| Run 4 | 49 | 9506.3ms | 10454.4ms | 10931.1ms | 0.00% | Uncapped Stress Test |
| **Run 5** | **94** | **4790ms** | **5530ms** | **—** | **0.00%** | **Post RC-1 fix: Redis-buffered clicks** |

### Run 5: 2026-08-30-10h21 (500 Users) — Post RC-1 Fix

- **Git SHA**: `c5fd50e`
- **Host**: `http://localhost:8080`
- **Duration**: 2 minutes (30s ramp-up, 1m sustained, 30s ramp-down)
- **Short Code**: `y38jwpz` (single code, all VUs target same code)

#### Configuration

| Parameter | Value |
|---|---|
| VUs | 500 |
| Ramp-up | 30s → 500 |
| Sustain | 1m at 500 |
| Ramp-down | 30s → 0 |
| Sleep between requests | 100ms |
| Threshold: p95 | < 100ms |
| Threshold: error rate | < 1% |

#### Results

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Total requests | 11,289 | — | — |
| RPS (avg) | 94.0 | — | — |
| Error rate | 0.00% | < 1% | PASS |
| p50 | 4,790ms | — | — |
| p95 | 5,530ms | < 100ms | FAIL |
| Max | 5,880ms | — | — |

#### Analysis

**What improved (RC-1 fix):**
- RPS increased from ~50 → 94 (**+88% throughput**)
- p50 decreased from 9,300ms → 4,790ms (**-48% latency**)
- p95 decreased from 10,500ms → 5,530ms (**-47% latency**)
- 0% error rate maintained

**Why p95 is still above 100ms:**
The redirect hot path now touches only Redis (no Postgres writes), but the **synchronous concurrency model** (RC-2) remains the bottleneck:
- Each request occupies one of AnyIO's **40 default threadpool threads** for its entire duration (Redis INCR + RPUSH + UA parsing + JSON serialization)
- 500 VUs competing for 40 threads → queueing at the threadpool level
- The sync Redis client (`redis-py`) blocks the thread on each call

**Remaining bottlenecks (in priority order):**
1. **RC-2**: Sync routes + 40-thread ceiling (convert to `async def` + async Redis)
2. **RC-3**: bcrypt cost on auth routes (not relevant to this redirect-only test)
3. **RC-4**: Default DB pool (not relevant to this redirect-only test)

---

## 3. Detailed Locust Test Reports (Per-Endpoint Breakdown)

### Run 1: 2026-08-06-09h13 (500 Users)

- **File**: `Locust_2026-08-06-09h13_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 7 minutes and 54 seconds
- **Start**: 2026-08-06T03:43:38Z
- **End**: 2026-08-06T03:51:32Z
- **Users**: 500

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| POST | `/api/v1/auth/login` | 303 | 269 | 257.5s | 4.4s | 303.0s | 336.0s | 428.0s | 428.0s | 0.6 | 0.6 | 88.78% |
| POST | `/api/v1/auth/register` | 500 | 352 | 144.9s | 751.0ms | 152.0s | 333.0s | 334.0s | 334.6s | 1.1 | 0.7 | 70.40% |
| POST | `/api/v1/urls` | 11,523 | 11,516 | 421.1ms | 4.0ms | 8ms | 20ms | 230ms | 459.4s | 24.3 | 24.3 | 99.94% |
| **ALL** | **Aggregated** | **12,326** | **12,137** | **12.6s** | **4.0ms** | **9ms** | **68.0s** | **307.0s** | **459.4s** | **26.0** | **25.6** | **98.47%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| 401 Unauthorized | 11,557 |
| 500 Server Error | 578 |
| Connection Error | 2 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/urls')` | 11,508 |
| POST | `/api/v1/auth/register` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/regi...` | 352 |
| POST | `/api/v1/auth/login` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/login')` | 220 |
| POST | `/api/v1/auth/login` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/auth/login')` | 49 |
| POST | `/api/v1/urls` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/urls')` | 6 |
| POST | `/api/v1/urls` | `RemoteDisconnected('Remote end closed connection without response')` | 2 |

</details>

---

### Run 2: 2026-08-06-09h26 (500 Users)

- **File**: `Locust_2026-08-06-09h26_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 6 minutes and 14 seconds
- **Start**: 2026-08-06T03:56:43Z
- **End**: 2026-08-06T04:02:57Z
- **Users**: 500

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET | `/[short_code]` | 989 | 0 | 26.7ms | 17.0ms | 26ms | 33ms | 37ms | 127.0ms | 2.6 | 0.0 | 0.00% |
| POST | `/api/v1/auth/login` | 1 | 0 | 431.4ms | 431.0ms | 431.4ms | 430ms | 430ms | 431.0ms | 0.0 | 0.0 | 0.00% |
| POST | `/api/v1/auth/register` | 1 | 0 | 10.3s | 10.3s | 10.3s | 10.0s | 10.0s | 10.3s | 0.0 | 0.0 | 0.00% |
| POST | `/api/v1/urls` | 123 | 63 | 27.1ms | 14.0ms | 27ms | 36ms | 51ms | 167.0ms | 0.3 | 0.2 | 51.22% |
| **ALL** | **Aggregated** | **1,114** | **63** | **36.3ms** | **14.0ms** | **26ms** | **34ms** | **40ms** | **10.3s** | **3.0** | **0.2** | **5.66%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| 429 Rate Limited | 63 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `HTTPError('429 Client Error: Too Many Requests for url: /api/v1/urls')` | 63 |

</details>

---

### Run 3: 2026-08-06-09h33 (500 Users)

- **File**: `Locust_2026-08-06-09h33_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 4 minutes and 45 seconds
- **Start**: 2026-08-06T04:03:56Z
- **End**: 2026-08-06T04:08:41Z
- **Users**: 500

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| POST | `/api/v1/auth/login` | 97 | 75 | 124.0s | 3.6s | 125.0s | 241.0s | 272.0s | 271.6s | 0.3 | 0.3 | 77.32% |
| POST | `/api/v1/auth/register` | 421 | 271 | 115.4s | 738.0ms | 122.0s | 272.0s | 275.0s | 277.0s | 1.5 | 1.0 | 64.37% |
| POST | `/api/v1/urls` | 3,737 | 3,737 | 92.3ms | 4.0ms | 9ms | 12ms | 26ms | 153.9s | 13.1 | 13.1 | 100.00% |
| **ALL** | **Aggregated** | **4,255** | **4,083** | **14.3s** | **4.0ms** | **9ms** | **126.0s** | **247.0s** | **277.0s** | **14.9** | **14.3** | **95.96%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| 401 Unauthorized | 3,735 |
| 500 Server Error | 348 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/urls')` | 3,735 |
| POST | `/api/v1/auth/register` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/regi...` | 271 |
| POST | `/api/v1/auth/login` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/login')` | 75 |
| POST | `/api/v1/urls` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/urls')` | 2 |

</details>

---

### Run 4: 2026-08-27-20h17 (500 Users)

- **File**: `Locust_2026-08-27-20h17_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 2 minutes and 58 seconds
- **Start**: 2026-08-27T14:47:18Z
- **End**: 2026-08-27T14:50:16Z
- **Users**: 500

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET | `/[short_code]` | 50 | 3 | 8.1s | 276.0ms | 1.4s | 58.0s | 64.0s | 63.7s | 0.3 | 0.0 | 6.00% |
| POST | `/api/v1/auth/login` | 86 | 20 | 23.2s | 729.0ms | 3.7s | 90.0s | 91.0s | 91.0s | 0.5 | 0.1 | 23.26% |
| POST | `/api/v1/auth/register` | 249 | 136 | 60.4s | 879.0ms | 60.0s | 144.0s | 144.0s | 144.8s | 1.4 | 0.8 | 54.62% |
| POST | `/api/v1/urls` | 758 | 748 | 2.7s | 5.0ms | 9ms | 7.1s | 66.0s | 117.8s | 4.3 | 4.2 | 98.68% |
| **ALL** | **Aggregated** | **1,143** | **907** | **17.1s** | **5.0ms** | **12ms** | **117.0s** | **144.0s** | **144.8s** | **6.5** | **5.1** | **79.35%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| 401 Unauthorized | 690 |
| 500 Server Error | 182 |
| 429 Rate Limited | 35 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/urls')` | 690 |
| POST | `/api/v1/auth/register` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/regi...` | 136 |
| POST | `/api/v1/urls` | `HTTPError('429 Client Error: Too Many Requests for url: /api/v1/urls')` | 35 |
| POST | `/api/v1/urls` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/urls')` | 23 |
| POST | `/api/v1/auth/login` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/login')` | 20 |
| GET | `/[short_code]` | `HTTPError('500 Server Error: Internal Server Error for url: /[short_code]')` | 3 |

</details>

---

### Run 5: 2026-08-27-20h24 (500 Users)

- **File**: `Locust_2026-08-27-20h24_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 6 minutes and 54 seconds
- **Start**: 2026-08-27T14:54:50Z
- **End**: 2026-08-27T15:01:44Z
- **Users**: 500

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET | `/[short_code]` | 18,010 | 0 | 169.2ms | 13.0ms | 160ms | 370ms | 490ms | 1.3s | 43.5 | 0.0 | 0.00% |
| POST | `/api/v1/auth/login` | 100 | 33 | 51.3s | 34.0s | 61.0s | 63.0s | 90.0s | 89.6s | 0.2 | 0.1 | 33.00% |
| POST | `/api/v1/auth/register` | 100 | 2 | 15.2s | 12.1s | 14.0s | 18.0s | 41.0s | 40.7s | 0.2 | 0.0 | 2.00% |
| POST | `/api/v1/urls` | 9,480 | 9,420 | 388.1ms | 2.0ms | 71ms | 440ms | 760ms | 61.2s | 22.9 | 22.8 | 99.37% |
| **ALL** | **Aggregated** | **27,690** | **9,455** | **483.0ms** | **2.0ms** | **140ms** | **400ms** | **1.0s** | **89.6s** | **66.9** | **22.8** | **34.15%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| 429 Rate Limited | 5,615 |
| 401 Unauthorized | 3,795 |
| 500 Server Error | 41 |
| Connection Error | 4 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `HTTPError('429 Client Error: Too Many Requests for url: /api/v1/urls')` | 5,615 |
| POST | `/api/v1/urls` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/urls')` | 3,793 |
| POST | `/api/v1/auth/login` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/login')` | 31 |
| POST | `/api/v1/urls` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/urls')` | 8 |
| POST | `/api/v1/urls` | `RemoteDisconnected('Remote end closed connection without response')` | 4 |
| POST | `/api/v1/auth/login` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/auth/login')` | 2 |
| POST | `/api/v1/auth/register` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/regi...` | 2 |

</details>

---

### Run 6: 2026-08-28-17h07 (500 Users)

- **File**: `Locust_2026-08-28-17h07_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 8 minutes and 55 seconds
- **Start**: 2026-08-28T11:37:52Z
- **End**: 2026-08-28T11:46:47Z
- **Users**: 500

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET | `/[short_code]` | 5,582 | 0 | 744.2ms | 335.0ms | 690ms | 1.1s | 1.6s | 29.0s | 10.4 | 0.0 | 0.00% |
| POST | `/api/v1/auth/login` | 500 | 437 | 220.6s | 62.6s | 226.0s | 363.0s | 364.0s | 389.5s | 0.9 | 0.8 | 87.40% |
| POST | `/api/v1/auth/register` | 500 | 3 | 19.3s | 1.7s | 19.0s | 35.0s | 37.0s | 64.0s | 0.9 | 0.0 | 0.60% |
| POST | `/api/v1/urls` | 46,042 | 45,386 | 135.5ms | 3.0ms | 8ms | 320ms | 1.1s | 90.2s | 86.0 | 84.8 | 98.58% |
| **ALL** | **Aggregated** | **52,624** | **45,826** | **2.5s** | **3.0ms** | **9ms** | **820ms** | **36.0s** | **389.5s** | **98.3** | **85.6** | **87.08%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| 401 Unauthorized | 45,266 |
| 500 Server Error | 445 |
| Connection Error | 115 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/urls')` | 45,263 |
| POST | `/api/v1/auth/login` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/login')` | 434 |
| POST | `/api/v1/urls` | `RemoteDisconnected('Remote end closed connection without response')` | 115 |
| POST | `/api/v1/urls` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/urls')` | 8 |
| POST | `/api/v1/auth/login` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/auth/login')` | 3 |
| POST | `/api/v1/auth/register` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/regi...` | 3 |

</details>

---

### Run 7: 2026-08-28-19h49 (500 Users)

- **File**: `Locust_2026-08-28-19h49_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 1 minute and 15 seconds
- **Start**: 2026-08-28T14:19:24Z
- **End**: 2026-08-28T14:20:39Z
- **Users**: 500

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GET | `/[short_code]` | 73 | 7 | 14.0s | 209.0ms | 2.8s | 61.0s | 62.0s | 62.1s | 1.0 | 0.1 | 9.59% |
| POST | `/api/v1/auth/login` | 71 | 8 | 18.6s | 744.0ms | 3.4s | 63.0s | 64.0s | 63.9s | 1.0 | 0.1 | 11.27% |
| POST | `/api/v1/auth/register` | 127 | 20 | 18.7s | 853.0ms | 3.6s | 62.0s | 62.0s | 62.2s | 1.7 | 0.3 | 15.75% |
| POST | `/api/v1/urls` | 102 | 66 | 6.4s | 4.0ms | 11ms | 35.0s | 61.0s | 65.3s | 1.4 | 0.9 | 64.71% |
| **ALL** | **Aggregated** | **373** | **101** | **14.4s** | **4.0ms** | **2.2s** | **62.0s** | **63.0s** | **65.3s** | **5.0** | **1.4** | **27.08%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| 401 Unauthorized | 59 |
| 500 Server Error | 42 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `HTTPError('401 Client Error: Unauthorized for url: /api/v1/urls')` | 59 |
| POST | `/api/v1/auth/register` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/regi...` | 20 |
| POST | `/api/v1/auth/login` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/auth/login')` | 8 |
| GET | `/[short_code]` | `HTTPError('500 Server Error: Internal Server Error for url: /[short_code]')` | 7 |
| POST | `/api/v1/urls` | `HTTPError('500 Server Error: Internal Server Error for url: /api/v1/urls')` | 7 |

</details>

---

### Run 8: 2026-08-28-20h09 (350 Users)

- **File**: `Locust_2026-08-28-20h09_locustfile.py_http___localhost_8080.html`
- **Host**: `http://localhost:8080`
- **Duration**: 1 minute and 59 seconds
- **Start**: 2026-08-28T14:39:47Z
- **End**: 2026-08-28T14:41:46Z
- **Users**: 350

#### Per-Endpoint Statistics

| Method | Endpoint | # Requests | # Failures | Avg | Min | Med (p50) | p95 | p99 | Max | RPS | Fail/s | Error Rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| POST | `/api/v1/auth/login` | 350 | 350 | 41.2ms | 5.0ms | 37ms | 75ms | 160.0ms | 214.0ms | 2.9 | 2.9 | 100.00% |
| POST | `/api/v1/auth/register` | 350 | 350 | 160.9ms | 32.0ms | 150.0ms | 310.0ms | 390.0ms | 391.0ms | 2.9 | 2.9 | 100.00% |
| POST | `/api/v1/urls` | 13,763 | 13,763 | 5.8ms | 1.0ms | 4ms | 13ms | 41ms | 383.0ms | 115.5 | 115.5 | 100.00% |
| **ALL** | **Aggregated** | **14,463** | **14,463** | **10.4ms** | **1.0ms** | **4ms** | **37ms** | **170.0ms** | **391.0ms** | **121.3** | **121.3** | **100.00%** |

#### Error Breakdown

| Category | Count |
| :--- | ---: |
| Connection Error | 14,463 |

<details>
<summary>Detailed Error List</summary>

| Method | Endpoint | Error | Occurrences |
| :--- | :--- | :--- | ---: |
| POST | `/api/v1/urls` | `ConnectionRefusedError(111, 'Connection refused')` | 13,763 |
| POST | `/api/v1/auth/login` | `ConnectionRefusedError(111, 'Connection refused')` | 350 |
| POST | `/api/v1/auth/register` | `ConnectionRefusedError(111, 'Connection refused')` | 350 |

</details>

---

## 4. Performance Tuning Log

*Document any changes made to the infrastructure, database indexes, or application code here to see how they impact the metrics in the table above.*

| Date | Change | Files | Expected Impact |
|---|---|---|---|
| 2026-08-30 | **RC-1 fix: Redis-buffered click counting with background flush** — Removed synchronous DB writes (UPDATE urls + INSERT clicks + COMMIT) from the redirect hot path. Clicks are now buffered in Redis via `INCR` + `RPUSH` and flushed to Postgres in batches every 10s by a background worker. Also added: `expires_at` in cache payload (bug fix), negative caching for unknown codes. | `app/cache/click_buffer.py` (new), `app/cache/flush_worker.py` (new), `app/cache/metrics.py`, `app/api/redirect.py`, `app/main.py` | Redirect hot path touches only Redis on cache hit → sub-millisecond, no row-lock contention. Expected throughput: 1,000+ RPS (up from ~50 RPS). Postgres writes shrink from 2-per-request to 1 batch-per-10s. |
| 2026-08-30 | **k6 validation (Run 5)** — 500 VUs, 2 min, single short code. RPS: 50→94 (+88%), p50: 9.3s→4.8s (-48%), p95: 10.5s→5.5s (-47%), 0% errors. p95 still above 100ms threshold because sync concurrency model (RC-2, 40 threads) remains the bottleneck. | — | RC-1 fix validated. Next: RC-2 (async routes + async Redis) to remove threadpool ceiling. |
