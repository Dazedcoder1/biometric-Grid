from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, Holiday
from app.schemas.schemas import HolidayResponse

router = APIRouter()

@router.get("", response_model=List[HolidayResponse])
async def get_holidays(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of holidays for the current tenant"""
    stmt = select(Holiday).where(Holiday.tenant_id == current_user.tenant_id).order_by(Holiday.holiday_date)
    res = await db.execute(stmt)
    return res.scalars().all()