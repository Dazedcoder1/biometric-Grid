from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from typing import Optional
from datetime import datetime
from app.db.session import get_db
from app.api.dependencies import verify_tenant_api_key
from app.models.domain import Tenant, LeaveBalance, LeaveSettings
from app.services.notification_service import notify_single_user

router = APIRouter()


@router.get("/leaves")
async def list_leave_requests(
    status: Optional[str] = None,
    dept_id: Optional[int] = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: List all leave requests"""
    query = """
        SELECT l.leave_id, l.employee_id, u.name as employee_name, u.employee_code,
            d.department_name, l.leave_type, l.start_date, l.end_date, l.reason, l.status, l.created_at
        FROM leaves l
        JOIN users u ON l.employee_id = u.id
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE l.tenant_id = :tenant_id
    """
    params = {"tenant_id": tenant.id}
    
    if status:
        query += " AND l.status = :status"
        params["status"] = status
    if dept_id:
        query += " AND u.dept_id = :dept_id"
        params["dept_id"] = dept_id
    
    query += " ORDER BY l.created_at DESC"
    
    result = await db.execute(text(query), params)
    return result.mappings().all()


@router.get("/leaves/pending")
async def pending_leaves(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Get pending leave requests count"""
    result = await db.execute(text("""
        SELECT COUNT(*) as pending_count
        FROM leaves
        WHERE tenant_id = :tenant_id AND status = 'pending'
    """), {"tenant_id": tenant.id})
    return result.mappings().first()


@router.patch("/leaves/{leave_id}/approve")
async def approve_leave(
    leave_id: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Approve a leave request (final approval)"""
    
    # Get leave details
    leave_info = await db.execute(text("""
        SELECT l.employee_id, l.leave_type, l.start_date, l.end_date
        FROM leaves l
        WHERE l.leave_id = :leave_id AND l.tenant_id = :tenant_id
    """), {"leave_id": leave_id, "tenant_id": tenant.id})
    info = leave_info.mappings().first()
    
    if not info:
        raise HTTPException(404, "Leave request not found")
    
    # Calculate days requested
    days_requested = (info["end_date"] - info["start_date"]).days + 1
    
    # Check leave balance
    current_year = datetime.now().year
    balance_result = await db.execute(
        select(LeaveBalance).where(
            LeaveBalance.tenant_id == tenant.id,
            LeaveBalance.user_id == info["employee_id"],
            LeaveBalance.leave_type == info["leave_type"],
            LeaveBalance.year == current_year
        )
    )
    balance = balance_result.scalars().first()
    
    if not balance:
        raise HTTPException(400, f"No leave balance found for {info['leave_type']} leave. Please contact admin.")
    
    if balance.remaining_quota < days_requested:
        raise HTTPException(400, f"Insufficient {info['leave_type']} leave balance. Available: {balance.remaining_quota}, Requested: {days_requested}")
    
    # Update leave status
    result = await db.execute(text("""
        UPDATE leaves
        SET status = 'approved', approved_at = NOW(), approved_by = :tenant_id
        WHERE leave_id = :leave_id AND tenant_id = :tenant_id
        AND status IN ('pending', 'approved_by_dept')
    """), {"leave_id": leave_id, "tenant_id": tenant.id})
    
    if result.rowcount == 0:
        raise HTTPException(404, "Leave request not found or cannot be approved")
    
    # Deduct from balance
    await db.execute(text("""
        UPDATE leave_balances
        SET used_quota = used_quota + :days,
            remaining_quota = remaining_quota - :days,
            last_updated = NOW()
        WHERE tenant_id = :tenant_id 
        AND user_id = :user_id 
        AND leave_type = :leave_type 
        AND year = :year
    """), {
        "days": days_requested,
        "tenant_id": tenant.id,
        "user_id": info["employee_id"],
        "leave_type": info["leave_type"],
        "year": current_year
    })
    
    await db.commit()
    
    # NOTIFICATION: Notify employee
    await notify_single_user(
        db=db,
        tenant_id=tenant.id,
        actor_id=None,
        recipient_id=info["employee_id"],
        event_type="leave_approved_final",
        title="Leave Fully Approved",
        message=f"Your {info['leave_type']} leave from {info['start_date']} to {info['end_date']} has been fully approved",
        entity_type="Leave",
        entity_id=leave_id
    )
    
    return {"message": "Leave approved successfully"}


@router.patch("/leaves/{leave_id}/reject")
async def reject_leave(
    leave_id: int,
    reason: str = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Reject a leave request"""
    
    # Get leave details
    leave_info = await db.execute(text("""
        SELECT l.employee_id, l.leave_type, l.start_date, l.end_date
        FROM leaves l
        WHERE l.leave_id = :leave_id AND l.tenant_id = :tenant_id
    """), {"leave_id": leave_id, "tenant_id": tenant.id})
    info = leave_info.mappings().first()
    
    result = await db.execute(text("""
        UPDATE leaves
        SET status = 'rejected', rejection_reason = :reason, rejected_at = NOW()
        WHERE leave_id = :leave_id AND tenant_id = :tenant_id
    """), {"leave_id": leave_id, "tenant_id": tenant.id, "reason": reason})
    
    if result.rowcount == 0:
        raise HTTPException(404, "Leave request not found")
    
    await db.commit()
    
    # NOTIFICATION: Notify employee
    message = f"Your {info['leave_type']} leave from {info['start_date']} to {info['end_date']} was rejected"
    if reason:
        message += f". Reason: {reason}"
    
    await notify_single_user(
        db=db,
        tenant_id=tenant.id,
        actor_id=None,
        recipient_id=info["employee_id"],
        event_type="leave_rejected",
        title="Leave Rejected",
        message=message,
        entity_type="Leave",
        entity_id=leave_id
    )
    
    return {"message": "Leave rejected"}


@router.get("/leaves/stats")
async def leave_statistics(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Tenant Manager: Get leave statistics"""
    result = await db.execute(text("""
        SELECT 
            COUNT(*) as total_requests,
            COUNT(*) FILTER (WHERE status = 'pending') as pending,
            COUNT(*) FILTER (WHERE status = 'approved_by_dept') as dept_approved,
            COUNT(*) FILTER (WHERE status = 'approved') as approved,
            COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
            COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
        FROM leaves
        WHERE tenant_id = :tenant_id
    """), {"tenant_id": tenant.id})
    return result.mappings().first()


# =========================
# LEAVE BALANCE ENDPOINTS (TENANT)
# =========================

@router.get("/leave-balances")
async def get_leave_balances(
    year: Optional[int] = None,
    department_id: Optional[int] = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Get all leave balances for tenant"""
    
    if not year:
        year = datetime.now().year
    
    query = """
        SELECT 
            lb.id,
            lb.user_id,
            u.name as user_name,
            u.employee_code,
            lb.leave_type,
            lb.total_quota,
            lb.used_quota,
            lb.remaining_quota,
            lb.year,
            d.department_name
        FROM leave_balances lb
        JOIN users u ON lb.user_id = u.id
        LEFT JOIN departments d ON u.dept_id = d.department_id
        WHERE lb.tenant_id = :tenant_id AND lb.year = :year
    """
    
    params = {"tenant_id": tenant.id, "year": year}
    
    if department_id:
        query += " AND u.dept_id = :dept_id"
        params["dept_id"] = department_id
    
    query += " ORDER BY u.name"
    
    result = await db.execute(text(query), params)
    balances = result.mappings().all()
    
    return balances


@router.get("/leave-balances/settings")
async def get_leave_settings(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Get leave settings for tenant"""
    
    result = await db.execute(
        select(LeaveSettings).where(LeaveSettings.tenant_id == tenant.id)
    )
    settings = result.scalars().first()
    
    if not settings:
        # Create default settings
        settings = LeaveSettings(
            tenant_id=tenant.id,
            sick_leave_quota=12,
            casual_leave_quota=12,
            earned_leave_quota=15,
            reset_frequency="yearly",
            carry_forward_limit=0,
            auto_approve_limit=0
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return {
        "sick_leave_quota": settings.sick_leave_quota,
        "casual_leave_quota": settings.casual_leave_quota,
        "earned_leave_quota": settings.earned_leave_quota,
        "reset_frequency": settings.reset_frequency,
        "carry_forward_limit": settings.carry_forward_limit,
        "auto_approve_limit": settings.auto_approve_limit
    }


@router.put("/leave-balances/settings")
async def update_leave_settings(
    data: dict,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Update leave settings for tenant"""
    
    result = await db.execute(
        select(LeaveSettings).where(LeaveSettings.tenant_id == tenant.id)
    )
    settings = result.scalars().first()
    
    if not settings:
        settings = LeaveSettings(tenant_id=tenant.id)
        db.add(settings)
    
    if "sick_leave_quota" in data:
        settings.sick_leave_quota = data["sick_leave_quota"]
    if "casual_leave_quota" in data:
        settings.casual_leave_quota = data["casual_leave_quota"]
    if "earned_leave_quota" in data:
        settings.earned_leave_quota = data["earned_leave_quota"]
    if "reset_frequency" in data:
        settings.reset_frequency = data["reset_frequency"]
    if "carry_forward_limit" in data:
        settings.carry_forward_limit = data["carry_forward_limit"]
    if "auto_approve_limit" in data:
        settings.auto_approve_limit = data["auto_approve_limit"]
    
    settings.updated_at = datetime.now()
    
    await db.commit()
    await db.refresh(settings)
    
    return {"message": "Leave settings updated successfully"}


@router.post("/leave-balances/update")
async def update_leave_balance(
    data: dict,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Update leave balance for a user"""
    
    year = datetime.now().year
    
    # Check if balance exists
    result = await db.execute(
        select(LeaveBalance).where(
            LeaveBalance.tenant_id == tenant.id,
            LeaveBalance.user_id == data["user_id"],
            LeaveBalance.leave_type == data["leave_type"],
            LeaveBalance.year == year
        )
    )
    balance = result.scalars().first()
    
    if balance:
        old_total = balance.total_quota
        balance.total_quota = data["total_quota"]
        balance.remaining_quota = data["total_quota"] - balance.used_quota
        balance.last_updated = datetime.now()
    else:
        balance = LeaveBalance(
            tenant_id=tenant.id,
            user_id=data["user_id"],
            leave_type=data["leave_type"],
            total_quota=data["total_quota"],
            used_quota=0,
            remaining_quota=data["total_quota"],
            year=year
        )
        db.add(balance)
    
    await db.commit()
    
    return {"message": f"Leave balance updated for {data['leave_type']} leave"}


@router.post("/leave-balances/reset-year")
async def reset_leave_balances(
    year: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Reset leave balances for all users for a specific year"""
    
    # Get settings
    settings_result = await db.execute(
        select(LeaveSettings).where(LeaveSettings.tenant_id == tenant.id)
    )
    settings = settings_result.scalars().first()
    
    if not settings:
        raise HTTPException(400, "Leave settings not configured")
    
    # Get all active users
    users_result = await db.execute(text("""
        SELECT id FROM users 
        WHERE tenant_id = :tenant_id AND is_active = True
    """), {"tenant_id": tenant.id})
    users = users_result.fetchall()
    
    # Create balances for each user
    for user in users:
        for leave_type, quota in [
            ('sick', settings.sick_leave_quota),
            ('casual', settings.casual_leave_quota),
            ('earned', settings.earned_leave_quota)
        ]:
            # Check if balance already exists
            existing = await db.execute(
                select(LeaveBalance).where(
                    LeaveBalance.tenant_id == tenant.id,
                    LeaveBalance.user_id == user.id,
                    LeaveBalance.leave_type == leave_type,
                    LeaveBalance.year == year
                )
            )
            if not existing.scalars().first():
                balance = LeaveBalance(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    leave_type=leave_type,
                    total_quota=quota,
                    used_quota=0,
                    remaining_quota=quota,
                    year=year
                )
                db.add(balance)
    
    await db.commit()
    
    return {"message": f"Leave balances reset for year {year}"}


@router.get("/leave-balances/users/{user_id}")
async def get_user_leave_balance(
    user_id: int,
    year: Optional[int] = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Get leave balance for a specific user"""
    
    if not year:
        year = datetime.now().year
    
    result = await db.execute(
        select(LeaveBalance).where(
            LeaveBalance.tenant_id == tenant.id,
            LeaveBalance.user_id == user_id,
            LeaveBalance.year == year
        )
    )
    balances = result.scalars().all()
    
    return [
        {
            "leave_type": b.leave_type,
            "total_quota": b.total_quota,
            "used_quota": b.used_quota,
            "remaining_quota": b.remaining_quota
        }
        for b in balances
    ]