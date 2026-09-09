from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant

router = APIRouter()

class HolidayCreate(BaseModel):
    name: str
    holiday_date: date
    description: str = None

class HolidayUpdate(BaseModel):
    name: str
    holiday_date: date
    description: str = None

@router.get('/holidays')
async def list_holidays(year: int = None, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    query = "SELECT * FROM holidays WHERE tenant_id = :tenant_id"
    params = {"tenant_id": tenant.id}
    if year:
        query += " AND EXTRACT(YEAR FROM holiday_date) = :year"
        params["year"] = year
    query += " ORDER BY holiday_date"
    result = await db.execute(text(query), params)
    return result.mappings().all()

@router.post('/holidays')
async def create_holiday(data: HolidayCreate, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    await db.execute(text("INSERT INTO holidays (tenant_id, name, holiday_date, description) VALUES (:tenant_id, :name, :holiday_date, :description)"),
        {"tenant_id": tenant.id, "name": data.name, "holiday_date": data.holiday_date, "description": data.description})
    await db.commit()
    return {"message": "Holiday created"}

@router.put('/holidays/{holiday_id}')
async def update_holiday(holiday_id: int, data: HolidayUpdate, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("UPDATE holidays SET name=:name, holiday_date=:holiday_date, description=:description WHERE holiday_id=:holiday_id AND tenant_id=:tenant_id"),
        {"holiday_id": holiday_id, "tenant_id": tenant.id, "name": data.name, "holiday_date": data.holiday_date, "description": data.description})
    if result.rowcount == 0:
        raise HTTPException(404, "Holiday not found")
    await db.commit()
    return {"message": "Holiday updated"}

@router.delete('/holidays/{holiday_id}')
async def delete_holiday(holiday_id: int, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("DELETE FROM holidays WHERE holiday_id=:holiday_id AND tenant_id=:tenant_id"), {"holiday_id": holiday_id, "tenant_id": tenant.id})
    if result.rowcount == 0:
        raise HTTPException(404, "Holiday not found")
    await db.commit()
    return {"message": "Holiday deleted"}

@router.get('/holidays/upcoming')
async def upcoming_holidays(limit: int = 5, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM holidays WHERE tenant_id=:tenant_id AND holiday_date >= CURRENT_DATE ORDER BY holiday_date LIMIT :limit"), {"tenant_id": tenant.id, "limit": limit})
    return result.mappings().all()