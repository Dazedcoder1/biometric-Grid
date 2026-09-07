from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.api.dependencies import get_current_user, require_role
from app.models.domain import User

router = APIRouter()


@router.get("/dashboard")
async def org_admin_dashboard(
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db)
):
    dept_id   = current_user.dept_id
    tenant_id = current_user.tenant_id

    dept_info = await db.execute(text(
        "SELECT department_name FROM departments WHERE department_id = :dept_id"
    ), {"dept_id": dept_id})
    dept_name = dept_info.scalar()

    emp_stats = await db.execute(text("""
        SELECT COUNT(*) as total_employees,
               COUNT(*) FILTER (WHERE is_active = true) as active_employees,
               COUNT(*) FILTER (WHERE finger_id IS NOT NULL) as enrolled_employees
        FROM users WHERE tenant_id = :tenant_id AND dept_id = :dept_id AND role = 'employee'
    """), {"tenant_id": tenant_id, "dept_id": dept_id})
    emp_data = emp_stats.mappings().first()

    att_stats = await db.execute(text("""
        SELECT COUNT(DISTINCT user_id) as present_today,
               COUNT(DISTINCT user_id) FILTER (WHERE timestamp::time <= '09:15:00') as on_time,
               COUNT(DISTINCT user_id) FILTER (WHERE timestamp::time > '09:15:00')  as late
        FROM attendance_logs
        WHERE tenant_id = :tenant_id
          AND user_id IN (SELECT id FROM users WHERE dept_id = :dept_id AND role = 'employee')
          AND DATE(timestamp) = CURRENT_DATE AND record_type = 'IN'
    """), {"tenant_id": tenant_id, "dept_id": dept_id})
    att_data = att_stats.mappings().first()

    leave_stats = await db.execute(text("""
        SELECT COUNT(*) as pending_leaves FROM leaves l
        JOIN users u ON l.employee_id = u.id
        WHERE l.tenant_id = :tenant_id AND u.dept_id = :dept_id AND l.status = 'pending'
    """), {"tenant_id": tenant_id, "dept_id": dept_id})
    leave_data = leave_stats.mappings().first()

    return {
        "department": dept_name,
        "employees": {
            "total":    emp_data["total_employees"]    or 0,
            "active":   emp_data["active_employees"]   or 0,
            "enrolled": emp_data["enrolled_employees"] or 0,
        },
        "attendance_today": {
            "present": att_data["present_today"] or 0,
            "on_time": att_data["on_time"]       or 0,
            "late":    att_data["late"]           or 0,
            "absent":  (emp_data["active_employees"] or 0) - (att_data["present_today"] or 0),
        },
        "pending_leaves": leave_data["pending_leaves"] or 0,
    }
