from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, insert
from pydantic import BaseModel
from datetime import date
from typing import Optional
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, Notification

router = APIRouter()


class LeaveApplyRequest(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


async def create_leave_notifications_bg(
    tenant_id: int,
    employee_id: int,
    employee_name: str,
    dept_id: int,
    leave_type: str,
    start_date: date,
    end_date: date,
    db: AsyncSession
):
    """Background task: Create all leave notifications"""
    
    # Get org admin IDs
    org_admins = await db.execute(text("""
        SELECT id FROM users
        WHERE tenant_id = :tenant_id
        AND dept_id = :dept_id
        AND role = 'org_admin'
        AND is_active = true
    """), {
        "tenant_id": tenant_id,
        "dept_id": dept_id
    })
    admin_ids = [row[0] for row in org_admins.all()]
    
    notification_values = []
    
    # Org admin notifications
    for admin_id in admin_ids:
        notification_values.append({
            "tenant_id": tenant_id,
            "actor_id": employee_id,
            "actor_name": employee_name,
            "recipient_id": admin_id,
            "event_type": "leave_requested",
            "entity_type": "Leave",
            "entity_name": f"{employee_name} ({leave_type})",
            "title": "New Leave Request",
            "message": f"{employee_name} requested {leave_type} leave from {start_date} to {end_date}",
            "is_read": False
        })
    
    # Employee confirmation
    notification_values.append({
        "tenant_id": tenant_id,
        "actor_id": employee_id,
        "actor_name": employee_name,
        "recipient_id": employee_id,
        "event_type": "leave_submitted",
        "entity_type": "Leave",
        "entity_name": f"{leave_type} leave",
        "title": "Leave Request Submitted",
        "message": f"Your {leave_type} leave request from {start_date} to {end_date} has been submitted",
        "is_read": False
    })
    
    if notification_values:
        await db.execute(insert(Notification).values(notification_values))
        await db.commit()


# =========================
# SPECIFIC ROUTES FIRST
# =========================

@router.get("/leaves/balance")
async def leave_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get leave balance"""
    result = await db.execute(text("""
        SELECT 
            COUNT(*) FILTER (WHERE leave_type = 'sick' AND status IN ('approved', 'approved_by_dept')) as sick_taken,
            COUNT(*) FILTER (WHERE leave_type = 'casual' AND status IN ('approved', 'approved_by_dept')) as casual_taken,
            COUNT(*) FILTER (WHERE leave_type = 'earned' AND status IN ('approved', 'approved_by_dept')) as earned_taken
        FROM leaves
        WHERE employee_id = :user_id
        AND EXTRACT(YEAR FROM start_date) = EXTRACT(YEAR FROM CURRENT_DATE)
    """), {"user_id": current_user.id})
    
    taken = result.mappings().first()
    
    return {
        "sick": {"total": 12, "taken": taken["sick_taken"] or 0, "remaining": 12 - (taken["sick_taken"] or 0)},
        "casual": {"total": 12, "taken": taken["casual_taken"] or 0, "remaining": 12 - (taken["casual_taken"] or 0)},
        "earned": {"total": 15, "taken": taken["earned_taken"] or 0, "remaining": 15 - (taken["earned_taken"] or 0)}
    }


@router.get("/leaves/stats")
async def leave_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get leave statistics"""
    result = await db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'pending') as pending,
            COUNT(*) FILTER (WHERE status = 'approved_by_dept') as dept_approved,
            COUNT(*) FILTER (WHERE status = 'approved') as approved,
            COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
            COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
        FROM leaves
        WHERE employee_id = :user_id
    """), {"user_id": current_user.id})
    
    stats = result.mappings().first()
    
    return {
        "total": stats["total"] or 0,
        "pending": stats["pending"] or 0,
        "dept_approved": stats["dept_approved"] or 0,
        "approved": stats["approved"] or 0,
        "rejected": stats["rejected"] or 0,
        "cancelled": stats["cancelled"] or 0
    }


# =========================
# GENERIC ROUTES LAST
# =========================

@router.get("/leaves")
async def get_leaves(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get own leave requests"""
    result = await db.execute(text("""
        SELECT *
        FROM leaves
        WHERE employee_id = :user_id
        ORDER BY created_at DESC
    """), {"user_id": current_user.id})
    return result.mappings().all()


@router.post("/leaves")
async def apply_leave(
    data: LeaveApplyRequest,
    background_tasks: BackgroundTasks,  # ← ADDED
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Apply for leave - FAST with background tasks"""
    
    # 1. Check overlapping leaves
    overlap = await db.execute(text("""
        SELECT leave_id FROM leaves
        WHERE employee_id = :user_id
        AND status NOT IN ('rejected', 'cancelled')
        AND (
            (:start_date BETWEEN start_date AND end_date)
            OR (:end_date BETWEEN start_date AND end_date)
            OR (start_date BETWEEN :start_date AND :end_date)
        )
    """), {
        "user_id": current_user.id,
        "start_date": data.start_date,
        "end_date": data.end_date
    })
    
    if overlap.scalar():
        raise HTTPException(400, "Leave request overlaps with existing leave")
    
    # 2. Insert leave (SYNCHRONOUS - must happen before response)
    await db.execute(text("""
        INSERT INTO leaves (tenant_id, employee_id, leave_type, start_date, end_date, reason, status)
        VALUES (:tenant_id, :employee_id, :leave_type, :start_date, :end_date, :reason, 'pending')
    """), {
        "tenant_id": current_user.tenant_id,
        "employee_id": current_user.id,
        "leave_type": data.leave_type,
        "start_date": data.start_date,
        "end_date": data.end_date,
        "reason": data.reason
    })
    await db.commit()
    
    # 3. Schedule notifications in BACKGROUND
    background_tasks.add_task(
        create_leave_notifications_bg,
        tenant_id=current_user.tenant_id,
        employee_id=current_user.id,
        employee_name=current_user.name,
        dept_id=current_user.dept_id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        db=db
    )
    
    # 4. Return IMMEDIATELY - user doesn't wait for notifications!
    return {"message": "Leave applied successfully"}


@router.get("/leaves/{leave_id}")
async def leave_detail(
    leave_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get specific leave request"""
    result = await db.execute(text("""
        SELECT * FROM leaves
        WHERE leave_id = :leave_id AND employee_id = :user_id
    """), {"leave_id": leave_id, "user_id": current_user.id})
    
    leave = result.mappings().first()
    if not leave:
        raise HTTPException(404, "Leave request not found")
    return leave


@router.patch("/leaves/{leave_id}/cancel")
async def cancel_leave(
    leave_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Cancel leave request"""
    
    leave_info = await db.execute(text("""
        SELECT leave_type, start_date, end_date FROM leaves
        WHERE leave_id = :leave_id AND employee_id = :user_id
    """), {"leave_id": leave_id, "user_id": current_user.id})
    info = leave_info.mappings().first()
    
    if not info:
        raise HTTPException(404, "Leave request not found")
    
    result = await db.execute(text("""
        UPDATE leaves SET status = 'cancelled'
        WHERE leave_id = :leave_id AND employee_id = :user_id AND status = 'pending'
    """), {"leave_id": leave_id, "user_id": current_user.id})
    
    if result.rowcount == 0:
        raise HTTPException(404, "Leave request not found or cannot be cancelled")
    
    await db.commit()
    
    return {"message": "Leave cancelled"}