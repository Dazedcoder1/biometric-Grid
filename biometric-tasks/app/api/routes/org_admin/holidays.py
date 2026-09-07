from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.api.dependencies import require_role
from app.models.domain import User

router = APIRouter()

@router.get('/holidays')
async def list_holidays(current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM holidays WHERE tenant_id=:tenant_id ORDER BY holiday_date"), {"tenant_id": current_user.tenant_id})
    return result.mappings().all()

@router.get('/holidays/upcoming')
async def upcoming_holidays(limit: int = 5, current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM holidays WHERE tenant_id=:tenant_id AND holiday_date >= CURRENT_DATE ORDER BY holiday_date LIMIT :limit"), {"tenant_id": current_user.tenant_id, "limit": limit})
    return result.mappings().all()