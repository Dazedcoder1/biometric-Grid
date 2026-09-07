from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import date
from typing import Optional
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant

router = APIRouter()

@router.get('/attendance/today')
async def today_attendance(dept_id: Optional[int] = None, tenant: Tenant = Depends(verify_tenant_api_key), db: AsyncSession = Depends(get_db)):
    query = """
        SELECT u.id, u.name, u.employee_code, d.department_name,
               MIN(a.timestamp) FILTER (WHERE a.record_type='IN') as check_in,
               MAX(a.timestamp) FILTER (WHERE a.record_type='OUT') as check_out,
               CASE WHEN MIN(a.timestamp) FILTER (WHERE a.record_type='IN') IS NOT NULL THEN 'present' ELSE 'absent' END as status
        FROM users u LEFT JOIN departments d ON u.dept_id=d.department_id
        LEFT JOIN attendance_logs a ON u.id=a.user_id AND DATE(a.timestamp)=CURRENT_DATE
        WHERE u.tenant_id=:tenant_id AND u.role='employee' AND u.is_active=true
    """
    params = {"tenant_id": tenant.id}
    if dept_id: query += " AND u.dept_id=:dept_id"; params["dept_id"] = dept_id
    query += " GROUP BY u.id, d.department_name ORDER BY u.name"
    result = await db.execute(text(query), params)
    return result.mappings().all()