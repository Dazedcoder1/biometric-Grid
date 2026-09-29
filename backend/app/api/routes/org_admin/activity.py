"""
Recent activity in this Org Admin's department.

`orgApi.getActivityLog()` had no route behind it, so the Activity page showed
its error state on every load.

Built from notifications rather than from the credential-vault audit log:
this screen answers "what has been happening with my team" — leave requests,
attendance, joiners — not "who touched which secret". Those are different
questions with different sensitivities, and the vault has its own audit viewer
with its own permission.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.db.session import get_db
from app.models.domain import User

router = APIRouter()


@router.get("/activity")
async def department_activity(
    limit: int = Query(50, le=200),
    current_user: User = Depends(require_role("org_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            """
            SELECT n.notification_id AS id,
                   n.event_type,
                   n.title,
                   n.message,
                   n.created_at,
                   n.is_read,
                   n.entity_name,
                   -- actor_name is denormalised onto the row so the record
                   -- survives the actor being deleted; fall back to the live
                   -- user only when the stored copy is missing.
                   COALESCE(n.actor_name, actor.name) AS actor_name
              FROM notifications n
              LEFT JOIN users actor     ON actor.id = n.actor_id
              LEFT JOIN users recipient ON recipient.id = n.recipient_id
             WHERE n.tenant_id = :tenant_id
               -- Department scope via the recipient. An Org Admin with no
               -- department set sees the whole tenant, which matches how every
               -- other org route treats a null dept_id.
               AND (CAST(:dept_id AS INTEGER) IS NULL OR recipient.dept_id = :dept_id)
             ORDER BY n.created_at DESC
             LIMIT :limit
            """
        ),
        {
            "tenant_id": current_user.tenant_id,
            "dept_id": current_user.dept_id,
            "limit": limit,
        },
    )
    return result.mappings().all()
