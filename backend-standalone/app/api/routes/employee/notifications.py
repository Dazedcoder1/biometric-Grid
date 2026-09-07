from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, update
from datetime import datetime
from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, Notification

router = APIRouter()


@router.get("/notifications/unread-count")
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get count of unread notifications for current user"""
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_id == current_user.id,
            Notification.is_read == False,
            Notification.tenant_id == current_user.tenant_id
        )
    )
    
    return {"count": result.scalar() or 0}


@router.patch("/notifications/read-all")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read for current user"""
    await db.execute(
        update(Notification)
        .where(
            Notification.recipient_id == current_user.id,
            Notification.tenant_id == current_user.tenant_id
        )
        .values(is_read=True, read_at=datetime.utcnow())
    )
    await db.commit()
    return {"message": "All notifications marked as read"}


@router.patch("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark a single notification as read (only affects current user's copy)"""
    result = await db.execute(
        update(Notification)
        .where(
            Notification.notification_id == notification_id,
            Notification.recipient_id == current_user.id
        )
        .values(is_read=True, read_at=datetime.utcnow())
    )
    
    if result.rowcount == 0:
        raise HTTPException(404, "Notification not found")
    
    await db.commit()
    return {"message": "Notification marked as read"}


@router.get("/notifications")
async def get_notifications(
    limit: int = 50,
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all notifications for current user"""
    
    query = select(Notification).where(
        Notification.recipient_id == current_user.id,
        Notification.tenant_id == current_user.tenant_id
    )
    
    if unread_only:
        query = query.where(Notification.is_read == False)
    
    query = query.order_by(Notification.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    return [
        {
            "notification_id": n.notification_id,
            "actor_name": n.actor_name,
            "event_type": n.event_type,
            "entity_type": n.entity_type,
            "entity_name": n.entity_name,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "read_at": n.read_at,
            "created_at": n.created_at
        }
        for n in notifications
    ]