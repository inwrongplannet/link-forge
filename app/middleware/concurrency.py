"""ASGI middleware that limits concurrent in-flight requests.

When the semaphore is full (all connections busy), new requests wait in a
queue. If no slot becomes available within ``timeout`` seconds, the request
receives an honest 503 the load balancer can act on immediately.
"""

import asyncio
import logging
import time

from prometheus_client import Counter, Gauge
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

in_flight = Gauge(
    "linkforge_http_in_flight_requests",
    "Number of requests currently being processed",
)
rejected_total = Counter(
    "linkforge_http_concurrency_rejected_total",
    "Requests rejected (503) because the concurrency limit was hit",
)
queue_wait_seconds = Counter(
    "linkforge_http_concurrency_queue_wait_seconds",
    "Total time requests spent waiting for a concurrency slot",
)


class ConcurrencyLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_concurrent: int = 40, timeout: float = 5.0):
        super().__init__(app)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = timeout
        self.max_concurrent = max_concurrent

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ):
        # Liveness probe should never be gated
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        start = time.monotonic()
        try:
            async with asyncio.timeout(self.timeout):
                async with self.semaphore:
                    wait_time = time.monotonic() - start
                    queue_wait_seconds.inc(wait_time)
                    in_flight.inc()
                    try:
                        return await call_next(request)
                    finally:
                        in_flight.dec()
        except TimeoutError:
            rejected_total.inc()
            logger.warning(
                "Concurrency limit reached (%d in-flight); returning 503 for %s %s",
                self.max_concurrent,
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": "pool_exhausted",
                    "message": "Server is at capacity, retry later.",
                },
            )
