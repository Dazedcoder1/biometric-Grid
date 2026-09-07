"""
Shared task logic used by the tenant, org-admin and employee routers.

Kept out of the route modules so the three role layers can't drift apart on
validation or tenant scoping.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import (
    Department, GitHubRepo, Task, TaskComment, TaskPriority, TaskSource,
    TaskStatus, User,
)
from app.services import github_service
from app.services.notification_service import notify_single_user

VALID_STATUSES = {s.value for s in TaskStatus}
VALID_PRIORITIES = {p.value for p in TaskPriority}


def validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    return status


def validate_priority(priority: str) -> str:
    if priority not in VALID_PRIORITIES:
        raise HTTPException(400, f"priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}")
    return priority


async def assert_assignee_in_tenant(db: AsyncSession, tenant_id: int, user_id: Optional[int]):
    """
    Guard against assigning a task to somebody in another tenant.

    Without this an attacker could enumerate user ids across tenant boundaries
    by watching which assignments succeed.
    """
    if user_id is None:
        return
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
    ).scalars().first()
    if not user:
        raise HTTPException(404, "Assignee not found in this organisation")


async def assert_dept_in_tenant(db: AsyncSession, tenant_id: int, dept_id: Optional[int]):
    if dept_id is None:
        return
    dept = (
        await db.execute(
            select(Department).where(
                Department.department_id == dept_id,
                Department.tenant_id == tenant_id,
            )
        )
    ).scalars().first()
    if not dept:
        raise HTTPException(404, "Department not found in this organisation")


async def get_task_or_404(db: AsyncSession, tenant_id: int, task_id: int) -> Task:
    task = (
        await db.execute(
            select(Task).where(Task.id == task_id, Task.tenant_id == tenant_id)
        )
    ).scalars().first()
    if not task:
        raise HTTPException(404, "Task not found")
    return task


async def serialize_tasks(db: AsyncSession, tasks: list[Task]) -> list[dict]:
    """Attach assignee and department names in one round trip rather than N."""
    if not tasks:
        return []

    user_ids = {t.assigned_to for t in tasks if t.assigned_to}
    dept_ids = {t.dept_id for t in tasks if t.dept_id}

    users = {}
    if user_ids:
        rows = await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        users = {r[0]: r[1] for r in rows.all()}

    depts = {}
    if dept_ids:
        rows = await db.execute(
            select(Department.department_id, Department.department_name).where(
                Department.department_id.in_(dept_ids)
            )
        )
        depts = {r[0]: r[1] for r in rows.all()}

    out = []
    for t in tasks:
        out.append({
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "source": t.source,
            "status": t.status,
            "priority": t.priority,
            "github_repo": t.github_repo,
            "github_issue_number": t.github_issue_number,
            "github_url": t.github_url,
            "github_state": t.github_state,
            "github_labels": t.github_labels,
            "dept_id": t.dept_id,
            "dept_name": depts.get(t.dept_id),
            "assigned_to": t.assigned_to,
            "assignee_name": users.get(t.assigned_to),
            "created_by": t.created_by,
            "due_date": t.due_date,
            "completed_at": t.completed_at,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })
    return out


def build_task_query(
    tenant_id: int,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    source: Optional[str] = None,
    assigned_to: Optional[int] = None,
    dept_id: Optional[int] = None,
    search: Optional[str] = None,
):
    q = select(Task).where(Task.tenant_id == tenant_id)
    if status:
        q = q.where(Task.status == status)
    if priority:
        q = q.where(Task.priority == priority)
    if source:
        q = q.where(Task.source == source)
    if assigned_to is not None:
        q = q.where(Task.assigned_to == assigned_to)
    if dept_id is not None:
        q = q.where(Task.dept_id == dept_id)
    if search:
        q = q.where(Task.title.ilike(f"%{search}%"))
    return q.order_by(Task.updated_at.desc().nullslast(), Task.id.desc())


async def apply_status_change(task: Task, new_status: str):
    validate_status(new_status)
    task.status = new_status
    task.completed_at = (
        datetime.now(timezone.utc) if new_status == TaskStatus.DONE.value else None
    )


async def notify_assignment(
    db: AsyncSession, task: Task, actor_id: Optional[int], tenant_id: int
):
    """Tell the assignee. Never let a notification failure roll back the task."""
    if not task.assigned_to or task.assigned_to == actor_id:
        return
    try:
        await notify_single_user(
            db=db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            recipient_id=task.assigned_to,
            event_type="task_assigned",
            title="New task assigned",
            message=f"You have been assigned: {task.title}",
            entity_type="task",
            entity_id=task.id,
            entity_name=task.title,
        )
    except Exception:  # noqa: BLE001 - notification is best-effort
        pass


# ─── Push: app -> GitHub ──────────────────────────────────────────────────────
#
# Design rule for everything below: the local task is the source of truth and
# must already be committed before we talk to GitHub. Every push returns a
# warning string instead of raising, so a GitHub outage, a revoked token or a
# repo with issues disabled degrades to "saved locally, not mirrored" rather
# than losing the user's work.


async def _repo_for(db: AsyncSession, tenant_id: int, repo_id: Optional[int]) -> Optional[GitHubRepo]:
    if not repo_id:
        return None
    return (
        await db.execute(
            select(GitHubRepo).where(
                GitHubRepo.id == repo_id,
                GitHubRepo.tenant_id == tenant_id,
                GitHubRepo.is_active.is_(True),
            )
        )
    ).scalars().first()


async def _github_login_for(db: AsyncSession, user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    return await db.scalar(select(User.github_username).where(User.id == user_id))


async def default_repo_for(db: AsyncSession, tenant_id: int) -> Optional[GitHubRepo]:
    """The repo new tasks push to when nobody picks one."""
    return (
        await db.execute(
            select(GitHubRepo).where(
                GitHubRepo.tenant_id == tenant_id,
                GitHubRepo.is_default.is_(True),
                GitHubRepo.is_active.is_(True),
            )
        )
    ).scalars().first()


async def resolve_push_repo_id(
    db: AsyncSession,
    tenant_id: int,
    explicit_repo_id: Optional[int],
    keep_local: bool,
) -> Optional[int]:
    """
    Decide where a new task should be pushed.

    Precedence: an explicit choice wins; then an explicit opt-out; then the
    tenant's default repo. keep_local exists so "no repo selected" can mean
    "deliberately local" rather than silently inheriting the default.
    """
    if explicit_repo_id:
        return explicit_repo_id
    if keep_local:
        return None
    repo = await default_repo_for(db, tenant_id)
    return repo.id if repo else None


PRIORITY_LABEL_PREFIX = "priority:"


def merge_priority_label(existing_csv: Optional[str], priority: str) -> list[str]:
    """
    Build the label set for an issue: everything GitHub already has, minus any
    previous priority label, plus the current one.

    GitHub's PATCH replaces the whole label array, so sending only our own
    label would silently delete every label maintained on the GitHub side.
    """
    existing = [l.strip() for l in (existing_csv or "").split(",") if l.strip()]
    kept = [l for l in existing if not l.lower().startswith(PRIORITY_LABEL_PREFIX)]
    kept.append(f"{PRIORITY_LABEL_PREFIX}{priority}")
    # De-duplicate case-insensitively while preserving order.
    seen, out = set(), []
    for label in kept:
        if label.lower() not in seen:
            seen.add(label.lower())
            out.append(label)
    return out


async def push_new_task(db: AsyncSession, task: Task, repo_id: int) -> Optional[str]:
    """
    Open a GitHub issue for a freshly created local task.

    The issue number is written back onto the task immediately. That is what
    stops the echo: GitHub fires an `issues.opened` webhook for the issue we
    just created, and because the task already carries
    (tenant_id, github_repo, github_issue_number), upsert_issue() matches the
    existing row and updates it instead of inserting a duplicate.
    """
    repo = await _repo_for(db, task.tenant_id, repo_id)
    if repo is None:
        return "Selected repository is not configured or is inactive; task saved locally only."

    # Fall back to the repo's default assignee when the task has nobody on it.
    assignee = await _github_login_for(db, task.assigned_to)
    if not assignee and repo.default_assignee_id:
        assignee = await _github_login_for(db, repo.default_assignee_id)

    ok, result = await github_service.create_issue(
        repo,
        title=task.title,
        body=task.description or "",
        labels=merge_priority_label(task.github_labels, task.priority),
        assignees=[assignee] if assignee else None,
    )
    if not ok:
        return f"Task saved, but GitHub issue was not created: {result.get('error')}"

    number = result.get("number")

    # Race: GitHub fires the issues.opened webhook the moment the issue exists,
    # which can be before the commit below. At that point our task has no issue
    # number yet, so upsert_issue() finds no match and inserts a task of its
    # own. Adopt that row rather than colliding with it on the unique index —
    # the user is looking at *this* task, so this one wins.
    duplicate = (
        await db.execute(
            select(Task).where(
                Task.tenant_id == task.tenant_id,
                Task.github_repo == repo.full_name,
                Task.github_issue_number == number,
                Task.id != task.id,
            )
        )
    ).scalars().first()
    if duplicate is not None:
        await db.delete(duplicate)
        await db.flush()

    task.github_repo_id = repo.id
    task.github_repo = repo.full_name
    task.github_issue_number = number
    task.github_url = result.get("html_url")
    task.github_state = result.get("state")

    try:
        await db.commit()
    except IntegrityError:
        # Lost the race even so. The issue exists and is mirrored by the other
        # row, so leave the local task unlinked rather than 500-ing.
        await db.rollback()
        return (f"Issue #{number} was created on GitHub, but it is already "
                f"mirrored by another task, so this one was left unlinked.")
    # updated_at carries onupdate=func.now(), so the commit leaves it expired.
    # Refresh here or the caller's serialization triggers a lazy load outside
    # the async context and blows up with MissingGreenlet.
    await db.refresh(task)

    # An assignee GitHub silently dropped (not a collaborator) is worth saying.
    if assignee and not any(
        a.get("login", "").lower() == assignee.lower()
        for a in (result.get("assignees") or [])
    ):
        return (f"Issue #{task.github_issue_number} created, but GitHub did not accept "
                f"'{assignee}' as an assignee — they may not have access to the repo.")
    return None


async def push_task_update(db: AsyncSession, task: Task, changed: set[str]) -> Optional[str]:
    """Mirror title/description/status/assignee edits onto the linked issue."""
    if not task.github_issue_number or not task.github_repo_id:
        return None

    repo = await _repo_for(db, task.tenant_id, task.github_repo_id)
    if repo is None:
        return None

    fields: dict = {}
    if "title" in changed:
        fields["title"] = task.title
    if "description" in changed:
        fields["body"] = task.description or ""
    if "status" in changed:
        # Only Done maps to closed; the three open states are all "open".
        fields["state"] = "closed" if task.status == TaskStatus.DONE.value else "open"
    if "assigned_to" in changed:
        login = await _github_login_for(db, task.assigned_to)
        if not login and repo.default_assignee_id:
            login = await _github_login_for(db, repo.default_assignee_id)
        # [] deliberately clears assignees when nobody resolves.
        fields["assignees"] = [login] if login else []
    if "priority" in changed:
        # Merged, not replaced — see merge_priority_label.
        fields["labels"] = merge_priority_label(task.github_labels, task.priority)

    if not fields:
        return None

    ok, result = await github_service.update_issue(repo, task.github_issue_number, **fields)
    if not ok:
        return f"Saved locally, but GitHub was not updated: {result.get('error')}"

    if "state" in fields:
        task.github_state = fields["state"]
        await db.commit()
        await db.refresh(task)   # see push_new_task: onupdate expires updated_at
    return None


async def push_comment(db: AsyncSession, task: Task, comment: TaskComment) -> Optional[str]:
    """
    Mirror an app comment onto the issue.

    Prefixed with the author's name because GitHub attributes it to whoever owns
    the token, not to the person who wrote it in the app.
    """
    if not task.github_issue_number or not task.github_repo_id:
        return None

    repo = await _repo_for(db, task.tenant_id, task.github_repo_id)
    if repo is None:
        return None

    author = comment.author_name or "Someone"
    body = f"**{author}** (via GridSphere):\n\n{comment.body}"

    ok, result = await github_service.create_issue_comment(
        repo, task.github_issue_number, body
    )
    if not ok:
        return f"Comment saved, but not mirrored to GitHub: {result.get('error')}"

    comment.github_comment_id = result.get("id")
    await db.commit()
    await db.refresh(comment)
    return None


async def task_stats(db: AsyncSession, tenant_id: int, assigned_to: Optional[int] = None) -> dict:
    q = select(Task.status, func.count(Task.id)).where(Task.tenant_id == tenant_id)
    if assigned_to is not None:
        q = q.where(Task.assigned_to == assigned_to)
    rows = (await db.execute(q.group_by(Task.status))).all()

    counts = {s: 0 for s in VALID_STATUSES}
    for status, count in rows:
        counts[status] = count
    counts["total"] = sum(counts[s] for s in VALID_STATUSES)
    return counts
