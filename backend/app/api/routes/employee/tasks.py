"""
Employee-facing 'My Tasks'.

Read-mostly: an employee sees only tasks assigned to them, and the only field
they may change is status. Everything else is set by an admin.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.domain import Task, TaskComment, User
from app.schemas.task_schemas import CommentCreate, TaskStatusUpdate
from app.services import task_service as svc

router = APIRouter()


async def _own_task_or_404(db: AsyncSession, user: User, task_id: int) -> Task:
    """Scoped by assignee as well as tenant — an employee can't reach a peer's task."""
    task = (
        await db.execute(
            select(Task).where(
                Task.id == task_id,
                Task.tenant_id == user.tenant_id,
                Task.assigned_to == user.id,
            )
        )
    ).scalars().first()
    if not task:
        raise HTTPException(404, "Task not found or not assigned to you")
    return task


@router.get("/tasks")
async def my_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = svc.build_task_query(
        current_user.tenant_id,
        status=status,
        priority=priority,
        source=source,
        assigned_to=current_user.id,
        search=search,
    )
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "tasks": await svc.serialize_tasks(db, rows),
    }


@router.get("/tasks/stats")
async def my_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.task_stats(db, current_user.tenant_id, assigned_to=current_user.id)


@router.patch("/tasks/{task_id}/status")
async def update_own_status(
    task_id: int,
    data: TaskStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _own_task_or_404(db, current_user, task_id)
    await svc.apply_status_change(task, data.status)
    await db.commit()
    await db.refresh(task)

    # An employee marking their own task Done closes the linked issue.
    warning = await svc.push_task_update(db, task, {"status"})

    result = (await svc.serialize_tasks(db, [task]))[0]
    if warning:
        result["github_warning"] = warning
    return result


@router.get("/tasks/{task_id}/comments")
async def list_comments(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _own_task_or_404(db, current_user, task_id)
    rows = (
        await db.execute(
            select(TaskComment).where(TaskComment.task_id == task_id).order_by(TaskComment.created_at)
        )
    ).scalars().all()
    return [
        {"id": c.id, "task_id": c.task_id, "user_id": c.user_id,
         "author_name": c.author_name, "body": c.body, "created_at": c.created_at}
        for c in rows
    ]


@router.post("/tasks/{task_id}/comments", status_code=201)
async def add_comment(
    task_id: int,
    data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _own_task_or_404(db, current_user, task_id)
    comment = TaskComment(
        task_id=task_id, user_id=current_user.id,
        author_name=current_user.name, body=data.body,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    warning = await svc.push_comment(db, task, comment)

    return {"id": comment.id, "task_id": comment.task_id, "user_id": comment.user_id,
            "author_name": comment.author_name, "body": comment.body,
            "created_at": comment.created_at,
            "github_comment_id": comment.github_comment_id,
            **({"github_warning": warning} if warning else {})}
