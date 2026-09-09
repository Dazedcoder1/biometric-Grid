from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.api.dependencies import require_role
from app.models.domain import User
from app.services.notification_service import notify_single_user

router = APIRouter()

@router.get('/leaves')
async def list_department_leaves(current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT l.leave_id, u.name as employee_name, u.employee_code,
               l.leave_type, l.start_date, l.end_date, l.reason, l.status, l.created_at
        FROM leaves l JOIN users u ON l.employee_id=u.id
        WHERE l.tenant_id=:tenant_id AND u.dept_id=:dept_id ORDER BY l.created_at DESC
    """), {"tenant_id": current_user.tenant_id, "dept_id": current_user.dept_id})
    return result.mappings().all()

@router.patch('/leaves/{leave_id}/approve')
async def approve_leave(leave_id: int, current_user: User = Depends(require_role('org_admin')), db: AsyncSession = Depends(get_db)):
    leave_info = await db.execute(text("""
        SELECT l.employee_id, l.leave_type, l.start_date, l.end_date, u.name as employee_name
        FROM leaves l JOIN users u ON l.employee_id=u.id WHERE l.leave_id=:leave_id
    """), {"leave_id": leave_id})
    info = leave_info.mappings().first()
    if not info: raise HTTPException(404, "Leave not found")
    result = await db.execute(text("""
        UPDATE leaves l SET status='approved_by_dept', dept_approved_at=NOW(), dept_approved_by=:admin_id
        FROM users u WHERE l.leave_id=:leave_id AND l.employee_id=u.id AND u.dept_id=:dept_id AND l.tenant_id=:tenant_id
        RETURNING l.leave_id
    """), {"leave_id": leave_id, "dept_id": current_user.dept_id, "tenant_id": current_user.tenant_id, "admin_id": current_user.id})
    if result.rowcount == 0: raise HTTPException(404, "Leave not in your department")
    await db.commit()
    await notify_single_user(db, current_user.tenant_id, current_user.id, info["employee_id"], "leave_dept_approved", "Leave Approved (Department)", f"Your {info['leave_type']} leave was approved by department head")
    return {"message": "Leave approved at department level"}