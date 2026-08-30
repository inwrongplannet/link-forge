from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_async_db
from app.auth.dependencies import get_current_user
from app.models.url import Url
from app.models.click import Click
from app.schemas.analytics import AnalyticsSummary, DailyClicks

router = APIRouter(prefix="/api/v1/urls", tags=["analytics"])

@router.get("/{url_id}/analytics", response_model=AnalyticsSummary)
async def get_analytics(url_id: str, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Url).where(Url.id == url_id))
    url_row = result.scalar_one_or_none()
    if url_row is None or url_row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="URL not found")
        
    total_result = await db.execute(select(func.count()).select_from(Click).where(Click.url_id == url_id))
    total = total_result.scalar()
    
    daily_result = await db.execute(
        select(func.date(Click.clicked_at), func.count())
        .where(Click.url_id == url_id)
        .group_by(func.date(Click.clicked_at))
        .order_by(func.date(Click.clicked_at))
    )
    daily_rows = daily_result.all()
    
    async def top_n(column):
        rows_result = await db.execute(
            select(column, func.count()).where(Click.url_id == url_id).group_by(column)
        )
        rows = rows_result.all()
        return {str(k or "unknown"): v for k, v in rows}
        
    return AnalyticsSummary(
        total_clicks=total or 0,
        daily_clicks=[DailyClicks(date=str(d), clicks=c) for d, c in daily_rows],
        top_browsers=await top_n(Click.browser),
        top_devices=await top_n(Click.device),
        top_referrers=await top_n(Click.referrer),
    )
