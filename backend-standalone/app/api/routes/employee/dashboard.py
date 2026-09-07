from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get personal dashboard with today's attendance and monthly summary"""
    
    query = text("""
        SELECT
            MIN(timestamp) FILTER (WHERE DATE(timestamp) = CURRENT_DATE) as check_in,
            MAX(timestamp) FILTER (WHERE DATE(timestamp) = CURRENT_DATE) as check_out,
            COUNT(DISTINCT DATE(timestamp)) FILTER (
                WHERE DATE_TRUNC('month', timestamp) = DATE_TRUNC('month', CURRENT_DATE)
                AND record_type = 'IN'
            ) as present_days
        FROM attendance_logs
        WHERE user_id = :user_id
    """)
    
    result = await db.execute(query, {"user_id": current_user.id})
    data = result.mappings().first()
    
    return {
        "check_in": data["check_in"],
        "check_out": data["check_out"],
        "present_days": data["present_days"] or 0
    }