from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, Leave
from app.schemas.schemas import LeaveCreate, LeaveResponse, MessageResponse
from datetime import datetime

router = APIRouter()

@router.post("", response_model=LeaveResponse)
async def apply_leave(
    data: LeaveCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee applies for a leave"""
    new_leave = Leave(
        tenant_id=current_user.tenant_id,
        employee_id=current_user.id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        status="pending"
    )
    db.add(new_leave)
    await db.commit()
    await db.refresh(new_leave)
    return new_leave

@router.get("", response_model=List[LeaveResponse])
async def get_my_leaves(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get history of leaves for current user"""
    stmt = select(Leave).where(Leave.employee_id == current_user.id).order_by(Leave.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/balance")
async def get_leave_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Return remaining leave balance"""
    # Using the logic from the previous file but adapted to the new schema
    result = await db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE leave_type='sick' AND status IN ('approved','approved_by_dept')) as sick_taken,
               COUNT(*) FILTER (WHERE leave_type='casual' AND status IN ('approved','approved_by_dept')) as casual_taken,
               COUNT(*) FILTER (WHERE leave_type='earned' AND status IN ('approved','approved_by_dept')) as earned_taken
        FROM leaves WHERE employee_id=:user_id AND EXTRACT(YEAR FROM start_date)=EXTRACT(YEAR FROM CURRENT_DATE)
    """), {"user_id": current_user.id})
    taken = result.mappings().first()
    return {
        "sick":   {"total": 12, "taken": taken["sick_taken"] or 0,   "remaining": 12 - (taken["sick_taken"] or 0)},
        "casual": {"total": 12, "taken": taken["casual_taken"] or 0, "remaining": 12 - (taken["casual_taken"] or 0)},
        "earned": {"total": 15, "taken": taken["earned_taken"] or 0, "remaining": 15 - (taken["earned_taken"] or 0)},
    }

@router.patch("/{leave_id}/cancel", response_model=MessageResponse)
async def cancel_leave(
    leave_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Leave).where(Leave.leave_id == leave_id, Leave.employee_id == current_user.id)
    res = await db.execute(stmt)
    leave = res.scalars().first()
    
    if not leave:
        raise HTTPException(404, "Leave not found")
    if leave.status != "pending":
        raise HTTPException(400, "Can only cancel pending leaves")
        
    leave.status = "cancelled"
    await db.commit()
    return {"message": "Leave cancelled successfully"}

from sqlalchemy import text # Added missing import for balance logic