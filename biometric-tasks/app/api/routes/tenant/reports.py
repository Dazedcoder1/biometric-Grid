from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from datetime import date
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant

router = APIRouter()

@router.get('/reports/attendance')
async def attendance_report(start_date: date, end_date: date, dept_id: Optional[int] = None, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    query = """
        SELECT u.id, u.name, u.employee_code, d.department_name,
               COUNT(DISTINCT DATE(a.timestamp)) FILTER (WHERE a.record_type='IN') as days_present,
               COUNT(DISTINCT DATE(a.timestamp)) FILTER (WHERE a.record_type='IN' AND a.timestamp::time > '09:15:00') as days_late
        FROM users u LEFT JOIN departments d ON u.dept_id=d.department_id
        LEFT JOIN attendance_logs a ON u.id=a.user_id AND DATE(a.timestamp) BETWEEN :start_date AND :end_date
        WHERE u.tenant_id=:tenant_id AND u.role='employee' AND u.is_active=true
    """
    params = {"tenant_id": tenant.id, "start_date": start_date, "end_date": end_date}
    if dept_id: query += " AND u.dept_id=:dept_id"; params["dept_id"] = dept_id
    query += " GROUP BY u.id, d.department_name ORDER BY u.name"
    result = await db.execute(text(query), params)
    return result.mappings().all()