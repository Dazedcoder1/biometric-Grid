from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant

router = APIRouter()

class SettingsUpdate(BaseModel):
    office_start_time: str = '09:00:00'
    office_end_time: str = '18:00:00'
    late_threshold_minutes: int = 15
    working_days: str = '1,2,3,4,5'

@router.get('/settings')
async def get_settings(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM settings WHERE tenant_id=:tenant_id LIMIT 1"), {"tenant_id": tenant.id})
    settings = result.mappings().first()
    if not settings:
        return {"office_start_time": "09:00:00", "office_end_time": "18:00:00", "late_threshold_minutes": 15, "working_days": "1,2,3,4,5"}
    return settings

@router.put('/settings')
async def update_settings(data: SettingsUpdate, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    await db.execute(text("""
        INSERT INTO settings (tenant_id, office_start_time, office_end_time, late_threshold_minutes, working_days)
        VALUES (:tenant_id, :ost, :oet, :lt, :wd)
        ON CONFLICT (tenant_id) DO UPDATE SET office_start_time=EXCLUDED.office_start_time,
        office_end_time=EXCLUDED.office_end_time, late_threshold_minutes=EXCLUDED.late_threshold_minutes, working_days=EXCLUDED.working_days
    """), {"tenant_id": tenant.id, "ost": data.office_start_time, "oet": data.office_end_time, "lt": data.late_threshold_minutes, "wd": data.working_days})
    await db.commit()
    return {"message": "Settings updated"}

@router.get('/profile')
async def get_tenant_profile(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    return {"id": tenant.id, "name": tenant.name, "api_key": tenant.api_key, "created_at": tenant.created_at}


