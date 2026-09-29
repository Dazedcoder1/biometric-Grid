from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel, Field
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant
from app.api.routes.common.settings import DEFAULTS as COMMON_DEFAULTS

router = APIRouter()

class SettingsUpdate(BaseModel):
    office_start_time: str = '09:00:00'
    office_end_time: str = '18:00:00'
    late_threshold_minutes: int = 15
    working_days: str = '1,2,3,4,5'
    # The attendance screens have always shown and calculated against this; it
    # simply had no column and no way to be saved. See migration b7c8d9e0f1a2.
    min_working_hours: float = 9.0

@router.get('/settings')
async def get_settings(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM settings WHERE tenant_id=:tenant_id LIMIT 1"), {"tenant_id": tenant.id})
    settings = result.mappings().first()
    # Must stay in step with routes/common/settings.DEFAULTS — two different
    # defaults for the same absent row would make the same tenant's figures
    # depend on which screen you opened.
    if not settings:
        return {**COMMON_DEFAULTS, "is_default": True}
    return {**settings, "is_default": False}

@router.put('/settings')
async def update_settings(data: SettingsUpdate, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    await db.execute(text("""
        INSERT INTO settings (tenant_id, office_start_time, office_end_time, late_threshold_minutes, working_days, min_working_hours)
        VALUES (:tenant_id, :ost, :oet, :lt, :wd, :mwh)
        ON CONFLICT (tenant_id) DO UPDATE SET office_start_time=EXCLUDED.office_start_time,
        office_end_time=EXCLUDED.office_end_time, late_threshold_minutes=EXCLUDED.late_threshold_minutes,
        working_days=EXCLUDED.working_days, min_working_hours=EXCLUDED.min_working_hours
    """), {"tenant_id": tenant.id, "ost": data.office_start_time, "oet": data.office_end_time,
           "lt": data.late_threshold_minutes, "wd": data.working_days, "mwh": data.min_working_hours})
    await db.commit()
    return {"message": "Settings updated"}

class ApiKeyChange(BaseModel):
    api_key: str = Field(..., min_length=16, max_length=128)


@router.post('/change-api-key')
async def change_api_key(
    data: ApiKeyChange,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Replace this organisation's API key.

    The Change API Key page shipped without this route, so the form returned
    404 and the key could not be rotated at all — which matters most in the one
    situation you need it: a key that has leaked.

    Two things worth stating plainly, because both surprise people:

    * Every device and integration using the old key stops working the instant
      this returns. That is the point of rotation, but it is not reversible and
      the old value is not recoverable from here.
    * If you authenticated with the API key itself, the credential you are
      holding is the one being replaced. The response carries the new key
      because there is no other way to learn it.

    Uniqueness is enforced across all tenants: keys are looked up by value
    alone, so a collision would hand one organisation access to another's data.
    """
    clash = (await db.execute(
        select(Tenant).where(Tenant.api_key == data.api_key, Tenant.id != tenant.id)
    )).scalars().first()
    if clash:
        raise HTTPException(409, "That key is already in use. Choose another.")

    if data.api_key == tenant.api_key:
        raise HTTPException(400, "That is already this organisation's key.")

    row = (await db.execute(select(Tenant).where(Tenant.id == tenant.id))).scalars().first()
    row.api_key = data.api_key
    await db.commit()

    return {
        "message": "API key changed. Update every device and integration now — "
                   "the previous key stopped working immediately.",
        "api_key": data.api_key,
    }


@router.get('/profile')
async def get_tenant_profile(tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    return {"id": tenant.id, "name": tenant.name, "api_key": tenant.api_key, "created_at": tenant.created_at}


