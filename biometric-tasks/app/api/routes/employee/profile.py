from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User
from app.schemas.schemas import UserResponse, ProfileUpdate

router = APIRouter()

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