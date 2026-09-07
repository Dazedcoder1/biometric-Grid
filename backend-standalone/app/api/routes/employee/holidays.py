from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.future import select
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User

router = APIRouter()


# =========================
# GET ALL HOLIDAYS
# =========================

@router.get("/holidays")
async def get_holidays(
    current_user: User = Depends(get_current_user),  # ← Get full User object
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get all holidays for their tenant"""
    
    # current_user is already the User object, get tenant_id from it
    tenant_id = current_user.tenant_id

    result = await db.execute(text("""
        SELECT *
        FROM holidays
        WHERE tenant_id = :tenant_id
        ORDER BY holiday_date
    """), {"tenant_id": tenant_id})

    return result.mappings().all()


# =========================
# UPCOMING HOLIDAY
# =========================

@router.get("/holidays/upcoming")
async def upcoming_holiday(
    current_user: User = Depends(get_current_user),  # ← Get full User object
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get next upcoming holiday"""
    
    tenant_id = current_user.tenant_id

    result = await db.execute(text("""
        SELECT *
        FROM holidays
        WHERE tenant_id = :tenant_id
        AND holiday_date >= CURRENT_DATE
        ORDER BY holiday_date
        LIMIT 1
    """), {"tenant_id": tenant_id})

    return result.mappings().first()