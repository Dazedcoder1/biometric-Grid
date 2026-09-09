from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, update
from datetime import datetime
from typing import List
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, Notification
from app.schemas.schemas import NotificationResponse, MessageResponse

router = APIRouter()

@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(func.count(Notification.notification_id)).where(
            Notification.recipient_id == current_user.id,
            Notification.is_read == False
        )
    )
    return {"count": result.scalar() or 0}

@router.get("", response_model=List[NotificationResponse])
async def get_notifications(
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.recipient_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(50)
    
    res = await db.execute(stmt)
    return res.scalars().all()

@router.patch("/{id}/read", response_model=MessageResponse)
async def mark_read(
    id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = update(Notification).where(
        Notification.notification_id == id,
        Notification.recipient_id == current_user.id
    ).values(is_read=True, read_at=datetime.utcnow())
    
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(404, "Notification not found")
    await db.commit()
    return {"message": "Marked as read"}

@router.patch("/read-all", response_model=MessageResponse)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = update(Notification).where(
        Notification.recipient_id == current_user.id,
        Notification.is_read == False
    ).values(is_read=True, read_at=datetime.utcnow())
    
    await db.execute(stmt)
    await db.commit()
    return {"message": "All marked as read"}