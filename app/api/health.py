from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
import app.cache.redis_client as redis_module

router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    return {"status": "ok"}

import logging
logger = logging.getLogger(__name__)

@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_async_db)):
    checks = {"database": False, "redis": False}
    errors = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.error("Database readiness check failed: %s", e)
        errors["database"] = str(e)

    try:
        await redis_module.async_redis_client.ping()
        checks["redis"] = True
    except Exception as e:
        logger.error("Redis readiness check failed: %s", e)
        errors["redis"] = str(e)

    all_ready = all(checks.values())
    content = {"ready": all_ready, "checks": checks}
    if errors:
        content["errors"] = errors
        
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content=content
    )
