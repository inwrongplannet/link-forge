from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from app.models.url import Url
from app.utils.short_code import generate_short_code

MAX_RETRIES = 5

def create_short_url(db: Session, original_url: str, user_id=None, custom_alias: str | None = None, expires_at=None) -> Url:
    from urllib.parse import urlparse
    candidate = original_url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid URL format")
    original_url = candidate

    code = custom_alias or generate_short_code()
    for attempt in range(MAX_RETRIES):
        url_row = Url(original_url=original_url, short_code=code, user_id=user_id, expires_at=expires_at)
        db.add(url_row)
        try:
            db.commit()
            db.refresh(url_row)
            return url_row
        except IntegrityError:
            db.rollback()
            if custom_alias:
                raise ValueError(f"Alias '{custom_alias}' is already taken")
            code = generate_short_code()
            # retry with a fresh random code
    raise RuntimeError("Could not generate a unique short code after several attempts")


async def create_short_url_async(db: AsyncSession, original_url: str, user_id=None, custom_alias: str | None = None, expires_at=None) -> Url:
    from urllib.parse import urlparse
    candidate = original_url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid URL format")
    original_url = candidate

    code = custom_alias or generate_short_code()
    for attempt in range(MAX_RETRIES):
        url_row = Url(original_url=original_url, short_code=code, user_id=user_id, expires_at=expires_at)
        db.add(url_row)
        try:
            await db.commit()
            await db.refresh(url_row)
            return url_row
        except IntegrityError:
            await db.rollback()
            if custom_alias:
                raise ValueError(f"Alias '{custom_alias}' is already taken")
            code = generate_short_code()
    raise RuntimeError("Could not generate a unique short code after several attempts")

