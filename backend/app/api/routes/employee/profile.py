import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.core import activity
from app.core.security import hash_password, verify_password
from app.models.domain import User
from app.schemas.schemas import UserResponse, ProfileUpdate

router = APIRouter()


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        # Matches the rules enforced at /api/auth/change-password and stated
        # on the Change Password screens. Two different standards for the same
        # password would mean a value accepted here and refused there.
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number")
        return v

@router.get("/profile", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user's profile info"""
    return current_user

@router.put("/profile", response_model=UserResponse)
async def update_profile(
    data: ProfileUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's profile info"""
    changed = []
    if data.name and data.name != current_user.name:
        current_user.name = data.name
        changed.append("name")
    if data.email and data.email != current_user.email:
        current_user.email = data.email
        changed.append("email")

    if changed:
        await activity.log(
            db, request, action="user.profile_updated", tenant_id=current_user.tenant_id,
            target_type="user", target_id=current_user.id, actor=current_user,
            details={"fields": changed},
        )
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/profile/change-password")
async def change_password(
    data: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change your own password.

    The employee Profile page has always had this form; the route did not
    exist, so submitting it returned 404 and nobody could change their
    password from inside the app.

    The current password is required even though the caller is already
    authenticated. A live session is not proof that the person at the keyboard
    is the account holder — an unlocked laptop is enough — and re-entering the
    old password is what stops a passer-by locking someone out of their own
    account.
    """
    if not current_user.password_hash:
        raise HTTPException(
            400,
            "This account has no password set. Ask an administrator to set one.",
        )
    if not verify_password(data.old_password, current_user.password_hash):
        await activity.log(
            db, request, action="auth.password_change_failed", result="denied",
            reason="current password wrong", tenant_id=current_user.tenant_id,
            target_type="user", target_id=current_user.id, actor=current_user,
        )
        await db.commit()
        raise HTTPException(400, "Your current password is not correct.")
    if data.old_password == data.new_password:
        raise HTTPException(400, "The new password must be different from the old one.")

    was_temporary = bool(current_user.must_change_password)
    current_user.password_hash = hash_password(data.new_password)
    # Choosing your own password is what clears a temporary one from an admin.
    current_user.must_change_password = False
    await activity.log(
        db, request, action="auth.password_changed", tenant_id=current_user.tenant_id,
        target_type="user", target_id=current_user.id, actor=current_user,
        details={"replaced_temporary": was_temporary},
    )
    await db.commit()
    return {"message": "Password changed."}
