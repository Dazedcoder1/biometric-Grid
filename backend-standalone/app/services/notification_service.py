"""
Notification Service - Single table design with per-recipient rows
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text, func
from typing import List, Optional
from app.models.domain import Notification, User
import logging

logger = logging.getLogger(__name__)


async def create_notifications_for_recipients(
    db: AsyncSession,
    tenant_id: int,
    actor_id: int,
    recipient_ids: List[int],
    event_type: str,
    title: str,
    message: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
    """
    Create notification rows for multiple recipients.
    Each recipient gets their own row with independent read status.
    """
    
    # Get actor name once (denormalize)
    actor_name = None
    if actor_id:
        result = await db.execute(
            select(User.name).where(User.id == actor_id)
        )
        actor_name = result.scalar() or "System"
    else:
        actor_name = "System"
    
    # Batch insert - one row per recipient
    count = 0
    for recipient_id in recipient_ids:
        notification = Notification(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_name=actor_name,
            recipient_id=recipient_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            title=title,
            message=message,
            is_read=False
        )
        db.add(notification)
        count += 1
    
    await db.commit()
    logger.info(f"Created {count} notifications for event '{event_type}'")
    return count


async def notify_department_admins_except_actor(
    db: AsyncSession,
    tenant_id: int,
    dept_id: int,
    actor_id: int,
    event_type: str,
    title: str,
    message_template: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
    """
    Notify all Org Admins in a department EXCEPT the actor.
    Each admin gets their own notification row.
    """
    
    # Get all org admins in this department EXCEPT the actor
    result = await db.execute(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.dept_id == dept_id,
            User.role == "org_admin",
            User.is_active == True,
            User.id != actor_id
        )
    )
    admins = result.all()
    
    if not admins:
        logger.info(f"No other org admins to notify in dept {dept_id}")
        return 0
    
    recipient_ids = [admin[0] for admin in admins]
    message = message_template.format(entity_name=entity_name or "Unknown")
    
    return await create_notifications_for_recipients(
        db=db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        recipient_ids=recipient_ids,
        event_type=event_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name
    )


async def notify_all_department_admins(
    db: AsyncSession,
    tenant_id: int,
    dept_id: int,
    actor_id: int,
    event_type: str,
    title: str,
    message_template: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
    """
    Notify ALL Org Admins in a department (including the actor).
    Used for leave requests where actor is employee, not admin.
    """
    
    result = await db.execute(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.dept_id == dept_id,
            User.role == "org_admin",
            User.is_active == True
        )
    )
    admins = result.all()
    
    if not admins:
        logger.info(f"No org admins to notify in dept {dept_id}")
        return 0
    
    recipient_ids = [admin[0] for admin in admins]
    message = message_template.format(entity_name=entity_name or "Unknown")
    
    return await create_notifications_for_recipients(
        db=db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        recipient_ids=recipient_ids,
        event_type=event_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name
    )


async def notify_single_user(
    db: AsyncSession,
    tenant_id: int,
    actor_id: int,
    recipient_id: int,
    event_type: str,
    title: str,
    message: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
    """Notify a single user"""
    return await create_notifications_for_recipients(
        db=db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        recipient_ids=[recipient_id],
        event_type=event_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name
    )


async def notify_multiple_users(
    db: AsyncSession,
    tenant_id: int,
    actor_id: int,
    recipient_ids: List[int],
    event_type: str,
    title: str,
    message: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
    """Notify multiple specific users"""
    return await create_notifications_for_recipients(
        db=db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        recipient_ids=recipient_ids,
        event_type=event_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name
    )