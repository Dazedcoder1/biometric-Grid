from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User
from app.core.security import verify_password, hash_password

router = APIRouter()


# =========================
# SCHEMAS
# =========================

class ProfileUpdate(BaseModel):
    name: str | None = None
    email: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# =========================
# ROUTES
# =========================

@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get own profile"""
    
    result = await db.execute(text("""
        SELECT
            u.id,
            u.name,
            u.email,
            u.employee_code,
            u.finger_id,
            u.role,
            u.is_active,
            u.created_at,
            d.department_id,
            d.department_name
        FROM users u
        LEFT JOIN departments d ON d.department_id = u.dept_id
        WHERE u.id = :id
    """), {"id": current_user.id})
    
    profile = result.mappings().first()
    
    if not profile:
        raise HTTPException(404, "Profile not found")
    
    return profile


@router.put("/profile")
async def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Update own profile"""
    
    if data.name is not None:
        current_user.name = data.name
    
    if data.email is not None:
        # Check if email is already taken
        from sqlalchemy.future import select
        existing = await db.execute(
            select(User).where(User.email == data.email, User.id != current_user.id)
        )
        if existing.scalars().first():
            raise HTTPException(400, "Email already in use")
        current_user.email = data.email
    
    await db.commit()
    await db.refresh(current_user)
    
    return {
        "message": "Profile updated successfully",
        "profile": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "employee_code": current_user.employee_code
        }
    }


@router.put("/profile/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Change own password"""
    
    if not current_user.password_hash:
        raise HTTPException(400, "No password set for this account")
    
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(401, "Incorrect current password")
    
    current_user.password_hash = hash_password(data.new_password)
    await db.commit()
    
    return {"message": "Password updated successfully"}


@router.get("/profile/attendance-summary")
async def attendance_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Employee: Get personal attendance summary"""
    
    result = await db.execute(text("""
        SELECT
            COUNT(DISTINCT DATE(timestamp)) FILTER (
                WHERE DATE_TRUNC('month', timestamp) = DATE_TRUNC('month', CURRENT_DATE)
                AND record_type = 'IN'
            ) as present_days_this_month,
            MIN(timestamp) FILTER (WHERE DATE(timestamp) = CURRENT_DATE AND record_type = 'IN') as today_check_in,
            MAX(timestamp) FILTER (WHERE DATE(timestamp) = CURRENT_DATE AND record_type = 'OUT') as today_check_out
        FROM attendance_logs
        WHERE user_id = :user_id
    """), {"user_id": current_user.id})
    
    data = result.mappings().first()
    
    return {
        "today": {
            "check_in": data["today_check_in"],
            "check_out": data["today_check_out"]
        },
        "this_month": {
            "present_days": data["present_days_this_month"] or 0
        }
    }