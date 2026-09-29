import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.api.dependencies import get_current_user
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
        # Matches the rules already enforced at /api/auth/set-password and
        # stated on the Change Password screens. Two different standards for
        # the same password would mean a value accepted here and refused there.
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's profile info"""
    if data.name:
        current_user.name = data.name
    if data.email:
        current_user.email = data.email
        
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/profile/change-password")
async def change_password(
    data: PasswordChange,
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
        raise HTTPException(400, "Your current password is not correct.")
    if data.old_password == data.new_password:
        raise HTTPException(400, "The new password must be different from the old one.")

    current_user.password_hash = hash_password(data.new_password)
    await db.commit()
    return {"message": "Password changed."}