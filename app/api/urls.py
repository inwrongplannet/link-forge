import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from sqlalchemy import select, or_, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_db
from app.schemas.url import UrlCreateRequest, UrlResponse, UrlUpdateRequest
from app.services.url_service import create_short_url_async
from app.database.config import settings
from app.models.user import User
from app.models.url import Url
from app.auth.dependencies import get_current_user
import app.cache.redis_client as redis_module

router = APIRouter(prefix="/api/v1/urls", tags=["urls"])

def to_response(url_row) -> UrlResponse:
    return UrlResponse(
        id=str(url_row.id),
        short_code=url_row.short_code,
        short_url=f"{settings.base_url}/{url_row.short_code}",
        original_url=url_row.original_url,
        is_active=url_row.is_active,
        click_count=url_row.click_count,
        expires_at=url_row.expires_at,
        created_at=url_row.created_at,
    )

@router.post("", response_model=UrlResponse, status_code=status.HTTP_201_CREATED)
async def create_url(request: Request, response: Response, payload: UrlCreateRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    try:
        url_row = await create_short_url_async(
            db,
            original_url=str(payload.original_url),
            user_id=str(current_user.id),
            custom_alias=payload.custom_alias,
            expires_at=payload.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return to_response(url_row)

@router.patch("/{url_id}", response_model=UrlResponse)
async def update_url(url_id: uuid.UUID, payload: UrlUpdateRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Url).where(Url.id == url_id))
    url_row = result.scalar_one_or_none()
    if url_row is None:
        raise HTTPException(status_code=404, detail="URL not found")
        
    if str(url_row.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this URL")
        
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "original_url" and value is not None:
            value = str(value)
        setattr(url_row, field, value)
        
    await db.commit()
    await db.refresh(url_row)
    await redis_module.async_redis_client.delete(f"url:{url_row.short_code}")
    return to_response(url_row)

@router.delete("/{url_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_url(url_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Url).where(Url.id == url_id))
    url_row = result.scalar_one_or_none()
    if url_row is None:
        raise HTTPException(status_code=404, detail="URL not found")
        
    if str(url_row.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this URL")
        
    short_code = url_row.short_code
    await db.delete(url_row)
    await db.commit()
    await redis_module.async_redis_client.delete(f"url:{short_code}")
    return None

ALLOWED_SORT_FIELDS = {"created_at", "click_count", "short_code"}

@router.get("", response_model=list[UrlResponse])
async def list_my_urls(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    q: str | None = Query(None, description="Search original_url or short_code"),
    sort_by: str = Query("created_at", description="created_at | click_count | short_code"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if sort_by not in ALLOWED_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"sort_by must be one of {ALLOWED_SORT_FIELDS}")
        
    stmt = select(Url).where(Url.user_id == current_user.id)
    
    if q:
        stmt = stmt.where(or_(Url.original_url.ilike(f"%{q}%"), Url.short_code.ilike(f"%{q}%")))
        
    sort_column = getattr(Url, sort_by)
    stmt = stmt.order_by(desc(sort_column) if order == "desc" else asc(sort_column))
    
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [to_response(r) for r in rows]
