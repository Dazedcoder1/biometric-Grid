from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import date
from app.db.session import get_db
from app.api.dependencies import require_role
from app.models.domain import User

router = APIRouter()

@router.get('/attendance/today')
async def today_attendance(current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT u.id, u.name, u.employee_code,
               MIN(a.timestamp) FILTER (WHERE a.record_type='IN') as check_in,
               MAX(a.timestamp) FILTER (WHERE a.record_type='OUT') as check_out,
               CASE WHEN MIN(a.timestamp) FILTER (WHERE a.record_type='IN') IS NOT NULL THEN 'present' ELSE 'absent' END as status
        FROM users u LEFT JOIN attendance_logs a ON u.id=a.user_id AND DATE(a.timestamp)=CURRENT_DATE
        WHERE u.tenant_id=:tenant_id AND u.dept_id=:dept_id AND u.role='employee' AND u.is_active=true
        GROUP BY u.id ORDER BY u.name
    """), {"tenant_id": current_user.tenant_id, "dept_id": current_user.dept_id})
    return result.mappings().all()

@router.get('/attendance/date/{attendance_date}')
async def attendance_by_date(attendance_date: date, current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT u.id, u.name, u.employee_code,
               MIN(a.timestamp) FILTER (WHERE a.record_type='IN') as check_in,
               MAX(a.timestamp) FILTER (WHERE a.record_type='OUT') as check_out,
               CASE WHEN MIN(a.timestamp) FILTER (WHERE a.record_type='IN') IS NOT NULL THEN 'present' ELSE 'absent' END as status
        FROM users u LEFT JOIN attendance_logs a ON u.id=a.user_id AND DATE(a.timestamp)=:attendance_date
        WHERE u.tenant_id=:tenant_id AND u.dept_id=:dept_id AND u.role='employee' AND u.is_active=true
        GROUP BY u.id ORDER BY u.name
    """), {"tenant_id": current_user.tenant_id, "dept_id": current_user.dept_id, "attendance_date": attendance_date})
    return result.mappings().all()