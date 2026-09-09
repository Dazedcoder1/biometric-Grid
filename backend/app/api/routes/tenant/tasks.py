"""
Tenant-admin task management.

Auth matches the rest of the tenant layer: X-API-Key via verify_tenant_api_key.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_tenant_api_key
from app.db.session import get_db
from app.models.domain import Task, TaskComment, TaskSource, Tenant, User
from app.schemas.task_schemas import (
    CommentCreate, TaskCreate, TaskPushRequest, TaskUpdate,
)
from app.services import task_service as svc

router = APIRouter()


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    source: Optional[str] = None,
    assigned_to: Optional[int] = None,
    dept_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    q = svc.build_task_query(
        tenant.id, status, priority, source, assigned_to, dept_id, search
    )
    total = await db.scalar(
        select(func.count()).select_from(q.subquery())
    )
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "tasks": await svc.serialize_tasks(db, rows),
    }


@router.get("/tasks/stats")
async def stats(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await svc.task_stats(db, tenant.id)


@router.get("/tasks/assignable-users")
async def assignable_users(
    dept_id: Optional[int] = None,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Everyone in this tenant who can hold a task."""
    q = select(User.id, User.name, User.email, User.role, User.dept_id).where(
        User.tenant_id == tenant.id, User.is_active.is_(True)
    )
    if dept_id is not None:
        q = q.where(User.dept_id == dept_id)
    rows = (await db.execute(q.order_by(User.name))).all()
    return [
        {"id": r[0], "name": r[1], "email": r[2], "role": r[3], "dept_id": r[4]}
        for r in rows
    ]


@router.post("/tasks", status_code=201)
async def create_task(
    data: TaskCreate,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Manual task creation — the 'extra task assignment' path."""
    svc.validate_status(data.status)
    svc.validate_priority(data.priority)
    await svc.assert_assignee_in_tenant(db, tenant.id, data.assigned_to)
    await svc.assert_dept_in_tenant(db, tenant.id, data.dept_id)

    task = Task(
        tenant_id=tenant.id,
        title=data.title,
        description=data.description,
        source=TaskSource.MANUAL.value,
        status=data.status,
        priority=data.priority,
        dept_id=data.dept_id,
        assigned_to=data.assigned_to,
        due_date=data.due_date,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    await svc.notify_assignment(db, task, None, tenant.id)
    await db.commit()

    # Push AFTER the local commit, so a GitHub failure can't lose the task.
    # An explicit repo wins; otherwise the tenant's default is used unless the
    # caller opted out with keep_local.
    warning = None
    repo_id = await svc.resolve_push_repo_id(
        db, tenant.id, data.github_repo_id, data.keep_local
    )
    if repo_id:
        warning = await svc.push_new_task(db, task, repo_id)
        await db.refresh(task)

    payload = (await svc.serialize_tasks(db, [task]))[0]
    if warning:
        payload["github_warning"] = warning
    return payload


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    data: TaskUpdate,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    task = await svc.get_task_or_404(db, tenant.id, task_id)
    previous_assignee = task.assigned_to
    payload = data.model_dump(exclude_unset=True)
    changed = set(payload)

    if "status" in payload:
        await svc.apply_status_change(task, payload.pop("status"))
    if "priority" in payload:
        svc.validate_priority(payload["priority"])
    if "assigned_to" in payload:
        await svc.assert_assignee_in_tenant(db, tenant.id, payload["assigned_to"])
    if "dept_id" in payload:
        await svc.assert_dept_in_tenant(db, tenant.id, payload["dept_id"])

    for field, value in payload.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)

    if task.assigned_to and task.assigned_to != previous_assignee:
        await svc.notify_assignment(db, task, None, tenant.id)
        await db.commit()

    warning = await svc.push_task_update(db, task, changed)

    result = (await svc.serialize_tasks(db, [task]))[0]
    if warning:
        result["github_warning"] = warning
    return result


@router.post("/tasks/{task_id}/push")
async def push_task_to_github(
    task_id: int,
    data: TaskPushRequest,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Open an issue for a task that was created locally."""
    task = await svc.get_task_or_404(db, tenant.id, task_id)
    if task.github_issue_number:
        raise HTTPException(
            400,
            f"Already linked to {task.github_repo}#{task.github_issue_number}.",
        )

    repo_id = await svc.resolve_push_repo_id(db, tenant.id, data.github_repo_id, False)
    if not repo_id:
        raise HTTPException(
            400, "No repository given and no default repository is configured."
        )

    warning = await svc.push_new_task(db, task, repo_id)
    await db.refresh(task)
    result = (await svc.serialize_tasks(db, [task]))[0]
    if warning:
        result["github_warning"] = warning
    return result


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    task = await svc.get_task_or_404(db, tenant.id, task_id)
    if task.source == TaskSource.GITHUB.value:
        raise HTTPException(
            400,
            "This task mirrors a GitHub issue and would reappear on the next sync. "
            "Deactivate the repo instead, or close the issue on GitHub.",
        )
    await db.delete(task)
    await db.commit()
    return {"message": "Task deleted"}


# ─── Comments ─────────────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}/comments")
async def list_comments(
    task_id: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    await svc.get_task_or_404(db, tenant.id, task_id)
    rows = (
        await db.execute(
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": c.id, "task_id": c.task_id, "user_id": c.user_id,
            "author_name": c.author_name, "body": c.body, "created_at": c.created_at,
        }
        for c in rows
    ]


@router.post("/tasks/{task_id}/comments", status_code=201)
async def add_comment(
    task_id: int,
    data: CommentCreate,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    task = await svc.get_task_or_404(db, tenant.id, task_id)
    comment = TaskComment(
        task_id=task_id, user_id=None, author_name="Tenant Admin", body=data.body
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    warning = await svc.push_comment(db, task, comment)

    return {
        "id": comment.id, "task_id": comment.task_id, "user_id": comment.user_id,
        "author_name": comment.author_name, "body": comment.body,
        "created_at": comment.created_at,
        "github_comment_id": comment.github_comment_id,
        **({"github_warning": warning} if warning else {}),
    }
