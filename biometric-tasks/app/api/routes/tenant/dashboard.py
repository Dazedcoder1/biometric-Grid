from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant

router = APIRouter()


@router.get("/dashboard")
async def tenant_dashboard(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    dept_stats = await db.execute(text("""
        SELECT COUNT(*) as total_departments,
               COUNT(*) FILTER (WHERE is_active = true) as active_departments
        FROM departments WHERE tenant_id = :tenant_id
    """), {"tenant_id": tenant.id})
    dept_data = dept_stats.mappings().first()

    user_stats = await db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE role = 'org_admin') as org_admins,
               COUNT(*) FILTER (WHERE role = 'employee' AND is_active = true) as active_employees,
               COUNT(*) FILTER (WHERE role = 'employee' AND finger_id IS NOT NULL) as enrolled_employees
        FROM users WHERE tenant_id = :tenant_id
    """), {"tenant_id": tenant.id})
    user_data = user_stats.mappings().first()

    att_stats = await db.execute(text("""
        SELECT COUNT(DISTINCT user_id) as present_today,
               COUNT(DISTINCT user_id) FILTER (WHERE timestamp::time <= '09:15:00') as on_time,
               COUNT(DISTINCT user_id) FILTER (WHERE timestamp::time > '09:15:00')  as late
        FROM attendance_logs
        WHERE tenant_id = :tenant_id AND DATE(timestamp) = CURRENT_DATE AND record_type = 'IN'
    """), {"tenant_id": tenant.id})
    att_data = att_stats.mappings().first()

    recent = await db.execute(text("""
        SELECT u.name, u.employee_code, d.department_name, a.timestamp, a.record_type
        FROM attendance_logs a
        JOIN users u ON a.user_id = u.id
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE a.tenant_id = :tenant_id
        ORDER BY a.timestamp DESC LIMIT 10
    """), {"tenant_id": tenant.id})

    return {
        "organization": tenant.name,
        "departments": {"total": dept_data["total_departments"] or 0, "active": dept_data["active_departments"] or 0},
        "users": {
            "org_admins": user_data["org_admins"] or 0,
            "active_employees": user_data["active_employees"] or 0,
            "enrolled_employees": user_data["enrolled_employees"] or 0,
        },
        "attendance_today": {
            "present": att_data["present_today"] or 0,
            "on_time": att_data["on_time"] or 0,
            "late": att_data["late"] or 0,
        },
        "recent_activity": recent.mappings().all(),
    }
