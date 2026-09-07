"""
Notification Service - Single table design with per-recipient rows.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from app.models.domain import Notification, User
import logging

logger = logging.getLogger(__name__)


async def create_notifications_for_recipients(
    db: AsyncSession,
    tenant_id: int,
    actor_id: Optional[int],
    recipient_ids: List[int],
    event_type: str,
    title: str,
    message: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
    actor_name = "System"
    if actor_id:
        result = await db.execute(select(User.name).where(User.id == actor_id))
        actor_name = result.scalar() or "System"

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

    await db.flush()
    logger.info(f"Created {count} notifications for event '{event_type}'")
    return count


async def notify_single_user(
    db: AsyncSession,
    tenant_id: int,
    actor_id: Optional[int],
    recipient_id: int,
    event_type: str,
    title: str,
    message: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
    return await create_notifications_for_recipients(
        db=db, tenant_id=tenant_id, actor_id=actor_id,
        recipient_ids=[recipient_id], event_type=event_type,
        title=title, message=message, entity_type=entity_type,
        entity_id=entity_id, entity_name=entity_name
    )


async def notify_all_department_admins(
    db: AsyncSession,
    tenant_id: int,
    dept_id: int,
    actor_id: Optional[int],
    event_type: str,
    title: str,
    message: str,
    entity_type: str = None,
    entity_id: int = None,
    entity_name: str = None
) -> int:
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
        return 0

    recipient_ids = [admin[0] for admin in admins]
    return await create_notifications_for_recipients(
        db=db, tenant_id=tenant_id, actor_id=actor_id,
        recipient_ids=recipient_ids, event_type=event_type,
        title=title, message=message, entity_type=entity_type,
        entity_id=entity_id, entity_name=entity_name
    )


# Legacy compat shim used in some older route files
async def create_notification(
    db: AsyncSession,
    tenant_id: int,
    recipient_id: int,
    title: str,
    message: str,
    notif_type: str = "system"
) -> None:
    await notify_single_user(
        db=db, tenant_id=tenant_id, actor_id=None,
        recipient_id=recipient_id, event_type=notif_type,
        title=title, message=message
    )


async def notify_org_admins(
    db: AsyncSession,
    tenant_id: int,
    dept_id: int,
    title: str,
    message: str,
    notif_type: str = "system"
) -> None:
    await notify_all_department_admins(
        db=db, tenant_id=tenant_id, dept_id=dept_id,
        actor_id=None, event_type=notif_type, title=title, message=message
    )
