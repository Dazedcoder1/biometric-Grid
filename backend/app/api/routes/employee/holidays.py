from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, Holiday
from app.schemas.schemas import HolidayResponse

router = APIRouter()


# "/upcoming" must stay above any "/{holiday_id}" route added later, or the
# path parameter swallows it and the literal never matches.
@router.get("/upcoming", response_model=Optional[HolidayResponse])
async def get_upcoming_holiday(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """The next holiday on or after today, or null if none is scheduled.

    Returns 200 with a null body when there is nothing coming up. "No holiday
    this year" is not a missing resource, and a 404 here took the whole
    employee dashboard down with it: the dashboard fetches six endpoints in
    one Promise.all, so a single rejection blanked the page.
    """
    stmt = (
        select(Holiday)
        .where(
            Holiday.tenant_id == current_user.tenant_id,
            Holiday.holiday_date >= datetime.utcnow().date(),
        )
        .order_by(Holiday.holiday_date)
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalars().first()


@router.get("", response_model=List[HolidayResponse])
async def get_holidays(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of holidays for the current tenant"""
    stmt = select(Holiday).where(Holiday.tenant_id == current_user.tenant_id).order_by(Holiday.holiday_date)
    res = await db.execute(stmt)
    return res.scalars().all()