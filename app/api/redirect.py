import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.parser import extract_browser_and_device
from app.analytics.service import record_click
from app.cache.click_buffer import buffer_click
from app.cache.metrics import cache_hits, cache_misses, clicks_buffered
from app.cache.redis_client import redis_client
from app.database.session import get_db
from app.models.url import Url

CACHE_TTL_SECONDS = 300
NEGATIVE_CACHE_TTL_SECONDS = 60
MISS_SENTINEL = "__miss__"

router = APIRouter(tags=["redirect"])


@router.get("/{short_code}")
def redirect_to_original(short_code: str, request: Request, db: Session = Depends(get_db)):  # noqa: B008
    cache_key = f"url:{short_code}"
    cached = redis_client.get(cache_key)

    if cached:
        cache_hits.inc()

        if cached == MISS_SENTINEL:
            raise HTTPException(status_code=404, detail="Short URL not found")

        data = json.loads(cached)

        if data["is_active"] is False:
            raise HTTPException(status_code=410, detail="This link has been deactivated")

        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=410, detail="This link has expired")

        browser, device = extract_browser_and_device(request.headers.get("user-agent", ""))
        buffered = buffer_click(
            redis_client,
            short_code,
            data["id"],
            ip_address=request.client.host if request.client else None,
            browser=browser,
            device=device,
            referrer=request.headers.get("referer"),
        )
        if buffered:
            clicks_buffered.inc()

        return RedirectResponse(url=data["original_url"], status_code=302)

    cache_misses.inc()
    url_row = db.scalar(select(Url).where(Url.short_code == short_code))
    if url_row is None:
        redis_client.setex(cache_key, NEGATIVE_CACHE_TTL_SECONDS, MISS_SENTINEL)
        raise HTTPException(status_code=404, detail="Short URL not found")
    if not url_row.is_active:
        raise HTTPException(status_code=410, detail="This link has been deactivated")
    if url_row.expires_at and url_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This link has expired")

    cache_payload = {
        "id": str(url_row.id),
        "original_url": url_row.original_url,
        "is_active": url_row.is_active,
        "expires_at": url_row.expires_at.isoformat() if url_row.expires_at else None,
    }
    redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(cache_payload))

    browser, device = extract_browser_and_device(request.headers.get("user-agent", ""))
    buffered = buffer_click(
        redis_client,
        short_code,
        str(url_row.id),
        ip_address=request.client.host if request.client else None,
        browser=browser,
        device=device,
        referrer=request.headers.get("referer"),
    )
    if buffered:
        clicks_buffered.inc()

    if not buffered:
        record_click(db, url_row.id, request)
        db.commit()

    return RedirectResponse(url=url_row.original_url, status_code=302)
