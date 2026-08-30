"""Background worker that flushes buffered clicks from Redis to Postgres.

Runs periodically (default every 10 seconds). Each cycle:
1. SCANs Redis for keys matching clicks:count:*
2. Atomically drains each counter + event list
3. Batch UPDATEs url click_counts
4. Batch INSERTs click rows
5. COMMITs once

The ``flush_once()`` function is also used by tests to synchronously flush
without waiting for the background cycle.
"""

import asyncio
import logging
import threading
import uuid
from collections import defaultdict

import redis
from sqlalchemy import create_engine, text

from app.cache.click_buffer import drain_click_buffer
from app.cache.metrics import clicks_flushed, flush_cycles, flush_errors
from app.database.config import settings

logger = logging.getLogger("linkforge.flush_worker")

FLUSH_INTERVAL_SECONDS = 10
SCAN_COUNT = 100


def flush_once(r: redis.Redis, engine) -> int:
    """Run a single flush cycle. Returns the number of click events flushed."""
    total_events = 0

    try:
        cursor, keys = r.scan(cursor=0, match="clicks:count:*", count=SCAN_COUNT)
        while keys:
            deltas: dict[str, int] = defaultdict(int)
            all_events: list[dict] = []

            for key in keys:
                short_code = key.removeprefix("clicks:count:")
                if not short_code:
                    continue

                delta, events = drain_click_buffer(r, short_code)
                if delta > 0:
                    deltas[short_code] += delta
                all_events.extend(events)
                total_events += len(events)

            if deltas:
                _flush_counters(deltas, engine)

            if all_events:
                _flush_events(all_events, engine)

            cursor, keys = r.scan(cursor=cursor, match="clicks:count:*", count=SCAN_COUNT)

    except redis.RedisError:
        logger.exception("Redis error during flush cycle")
        return 0

    return total_events


def _flush_counters(deltas: dict[str, int], engine) -> None:
    """Batch UPDATE click_count for multiple URLs."""
    if not deltas:
        return

    with engine.begin() as conn:
        for short_code, delta in deltas.items():
            conn.execute(
                text("UPDATE urls SET click_count = click_count + :delta WHERE short_code = :code"),
                {"delta": delta, "code": short_code},
            )

    logger.debug("Flushed click counts for %d URLs", len(deltas))


def _flush_events(events: list[dict], engine) -> None:
    """Batch INSERT click events into the clicks table."""
    if not events:
        return

    rows = []
    for e in events:
        rows.append({
            "id": str(uuid.uuid4()),
            "url_id": e["url_id"],
            "ip_address": e.get("ip_address"),
            "browser": e.get("browser"),
            "device": e.get("device"),
            "referrer": e.get("referrer"),
            "clicked_at": e.get("clicked_at"),
        })

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clicks (id, url_id, ip_address, browser, device, referrer, clicked_at) "
                "VALUES (:id, :url_id, :ip_address, :browser, :device, :referrer, :clicked_at)"
            ),
            rows,
        )

    logger.debug("Flushed %d click events to Postgres", len(rows))


def run_flush_worker(
    r: redis.Redis | None = None,
    engine=None,
    interval: int = FLUSH_INTERVAL_SECONDS,
    stop_event: threading.Event | None = None,
) -> None:
    """Background loop that periodically flushes buffered clicks to Postgres.

    Intended to run in a daemon thread. Use ``stop_event`` for graceful shutdown.
    """
    if r is None:
        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    if engine is None:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
    if stop_event is None:
        stop_event = threading.Event()

    logger.info("Click flush worker started (interval=%ds)", interval)

    while not stop_event.is_set():
        stop_event.wait(timeout=interval)
        if stop_event.is_set():
            break
        try:
            flushed = flush_once(r, engine)
            flush_cycles.inc()
            if flushed:
                clicks_flushed.inc(flushed)
                logger.info("Flushed %d click events to Postgres", flushed)
        except Exception:
            flush_errors.inc()
            logger.exception("Unexpected error in flush worker")

    logger.info("Click flush worker stopped")


async def run_flush_worker_async(
    interval: int = FLUSH_INTERVAL_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Async background loop that periodically flushes buffered clicks to Postgres.

    Runs as an asyncio task in the event loop. Uses its own sync engine + sync Redis
    for the actual batch operations (acceptable for background batch work).
    """
    r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    if stop_event is None:
        stop_event = asyncio.Event()

    logger.info("Click flush worker started (interval=%ds)", interval)

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            break
        try:
            flushed = flush_once(r, engine)
            flush_cycles.inc()
            if flushed:
                clicks_flushed.inc(flushed)
                logger.info("Flushed %d click events to Postgres", flushed)
        except Exception:
            flush_errors.inc()
            logger.exception("Unexpected error in flush worker")

    logger.info("Click flush worker stopped")
