"""Redis-backed click buffering for the redirect hot path.

Instead of writing to Postgres on every redirect, we buffer click data in Redis
and flush to Postgres in batches via a background worker. This removes all DB
writes from the redirect hot path, eliminating the single-row lock contention
that capped throughput at ~50 RPS.
"""

import json
import logging
from datetime import datetime, timezone

import redis

logger = logging.getLogger("linkforge.click_buffer")


def buffer_click(
    r: redis.Redis,
    short_code: str,
    url_id: str,
    ip_address: str | None,
    browser: str,
    device: str,
    referrer: str | None,
    clicked_at: datetime | None = None,
) -> bool:
    """Buffer a click event in Redis for later batch flushing to Postgres.

    Returns True on success, False if Redis is unavailable (caller may fall
    back to synchronous DB writes).
    """
    if clicked_at is None:
        clicked_at = datetime.now(timezone.utc)

    event = {
        "url_id": url_id,
        "ip_address": ip_address,
        "browser": browser,
        "device": device,
        "referrer": referrer,
        "clicked_at": clicked_at.isoformat(),
    }

    try:
        pipe = r.pipeline()
        pipe.incr(f"clicks:count:{short_code}")
        pipe.rpush(f"clicks:events:{short_code}", json.dumps(event))
        pipe.execute()
        return True
    except redis.RedisError:
        logger.exception("Failed to buffer click for %s", short_code)
        return False


def drain_click_buffer(
    r: redis.Redis, short_code: str
) -> tuple[int, list[dict]]:
    """Atomically read and clear buffered click data for a short code.

    Returns (click_count_increment, list_of_click_events).
    """
    count_key = f"clicks:count:{short_code}"
    events_key = f"clicks:events:{short_code}"

    try:
        pipe = r.pipeline()
        pipe.get(count_key)
        pipe.delete(count_key)
        pipe.lrange(events_key, 0, -1)
        pipe.delete(events_key)
        results = pipe.execute()

        raw_count = results[0]
        delta = int(raw_count) if raw_count else 0

        raw_events = results[2]
        events = [json.loads(e) for e in raw_events] if raw_events else []

        return delta, events
    except redis.RedisError:
        logger.exception("Failed to drain click buffer for %s", short_code)
        return 0, []
