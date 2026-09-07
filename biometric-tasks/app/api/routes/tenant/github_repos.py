"""
Per-tenant GitHub repository configuration.

Tokens and webhook secrets are written encrypted and never read back out to a
client — GitHubRepoOut exposes only has_token / has_webhook_secret booleans.
"""

import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_tenant_api_key
from app.core import crypto
from app.db.session import get_db
from app.models.domain import GitHubRepo, Task, Tenant, User
from app.schemas.task_schemas import (
    GitHubRepoCreate, GitHubRepoOut, GitHubRepoUpdate, GitHubUsernameUpdate,
)
from app.services import github_service

router = APIRouter()


def _require_encryption():
    if not crypto.is_configured():
        raise HTTPException(
            503,
            "GITHUB_ENC_KEY is not set on the server, so GitHub tokens cannot be "
            "stored securely. Add it to .env and restart.",
        )


async def _clear_other_defaults(db: AsyncSession, tenant_id: int, keep_id: int | None):
    """
    Exactly one default per tenant.

    Enforced here rather than by a partial unique index, which would be
    Postgres-only and would fail the migration on any other backend.
    """
    others = (
        await db.execute(
            select(GitHubRepo).where(
                GitHubRepo.tenant_id == tenant_id,
                GitHubRepo.is_default.is_(True),
            )
        )
    ).scalars().all()
    for other in others:
        if other.id != keep_id:
            other.is_default = False


async def _assert_assignee(db: AsyncSession, tenant_id: int, user_id: int | None):
    if user_id is None:
        return
    found = (
        await db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
    ).scalars().first()
    if not found:
        raise HTTPException(404, "Default assignee not found in this organisation")


async def _serialize(db: AsyncSession, repo: GitHubRepo) -> dict:
    count = await db.scalar(
        select(func.count(Task.id)).where(
            Task.tenant_id == repo.tenant_id, Task.github_repo == repo.full_name
        )
    )
    assignee_name = None
    if repo.default_assignee_id:
        assignee_name = await db.scalar(
            select(User.name).where(User.id == repo.default_assignee_id)
        )
    return {
        "id": repo.id,
        "full_name": repo.full_name,
        "is_active": repo.is_active,
        "label_filter": repo.label_filter,
        "is_default": bool(repo.is_default),
        "default_assignee_id": repo.default_assignee_id,
        "default_assignee_name": assignee_name,
        "has_token": bool(repo.token_encrypted),
        "has_webhook_secret": bool(repo.webhook_secret_encrypted),
        "last_synced_at": repo.last_synced_at,
        "last_sync_error": repo.last_sync_error,
        "task_count": count or 0,
        "created_at": repo.created_at,
    }


@router.get("/github/repos", response_model=List[GitHubRepoOut])
async def list_repos(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(GitHubRepo).where(GitHubRepo.tenant_id == tenant.id).order_by(GitHubRepo.full_name)
        )
    ).scalars().all()
    return [await _serialize(db, r) for r in rows]


@router.post("/github/repos", status_code=201)
async def add_repo(
    data: GitHubRepoCreate,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    _require_encryption()

    full_name = data.full_name.strip().strip("/")
    if full_name.count("/") != 1:
        raise HTTPException(400, "full_name must be in 'owner/repo' form")

    exists = (
        await db.execute(
            select(GitHubRepo).where(
                GitHubRepo.tenant_id == tenant.id, GitHubRepo.full_name == full_name
            )
        )
    ).scalars().first()
    if exists:
        raise HTTPException(400, "That repository is already configured")

    # Fail fast on a bad token or typo'd repo rather than at first sync.
    check = await github_service.verify_repo_access(full_name, data.token)
    if not check.get("ok"):
        raise HTTPException(400, check.get("error", "Could not reach that repository"))

    # Generated when not supplied, so the caller always has a secret to paste
    # into GitHub's webhook form.
    webhook_secret = data.webhook_secret or secrets.token_urlsafe(32)

    await _assert_assignee(db, tenant.id, data.default_assignee_id)

    repo = GitHubRepo(
        tenant_id=tenant.id,
        full_name=full_name,
        token_encrypted=crypto.encrypt(data.token) if data.token else None,
        webhook_secret_encrypted=crypto.encrypt(webhook_secret),
        label_filter=data.label_filter,
        is_active=True,
        is_default=bool(data.is_default),
        default_assignee_id=data.default_assignee_id,
    )
    db.add(repo)
    await db.flush()
    if data.is_default:
        await _clear_other_defaults(db, tenant.id, repo.id)
    await db.commit()
    await db.refresh(repo)

    # First pull, so the board isn't empty while waiting on a webhook.
    result = await github_service.sync_repo(db, repo)
    await db.refresh(repo)

    payload = await _serialize(db, repo)
    payload["initial_sync"] = result
    # The only time the secret is ever returned — it can't be recovered later.
    payload["webhook_secret"] = webhook_secret
    payload["webhook_url_path"] = "/api/webhooks/github"
    return payload


@router.put("/github/repos/{repo_id}")
async def update_repo(
    repo_id: int,
    data: GitHubRepoUpdate,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    repo = (
        await db.execute(
            select(GitHubRepo).where(GitHubRepo.id == repo_id, GitHubRepo.tenant_id == tenant.id)
        )
    ).scalars().first()
    if not repo:
        raise HTTPException(404, "Repository not configured")

    payload = data.model_dump(exclude_unset=True)

    if "token" in payload:
        _require_encryption()
        repo.token_encrypted = crypto.encrypt(payload["token"]) if payload["token"] else None
    if "webhook_secret" in payload:
        _require_encryption()
        repo.webhook_secret_encrypted = (
            crypto.encrypt(payload["webhook_secret"]) if payload["webhook_secret"] else None
        )
    if "label_filter" in payload:
        repo.label_filter = payload["label_filter"]
    if "is_active" in payload:
        repo.is_active = payload["is_active"]
        # A deactivated repo can't remain the default target for new tasks.
        if not payload["is_active"]:
            repo.is_default = False
    if "default_assignee_id" in payload:
        await _assert_assignee(db, tenant.id, payload["default_assignee_id"])
        repo.default_assignee_id = payload["default_assignee_id"]
    if "is_default" in payload:
        repo.is_default = bool(payload["is_default"])
        if repo.is_default:
            if not repo.is_active:
                raise HTTPException(400, "An inactive repository cannot be the default")
            await _clear_other_defaults(db, tenant.id, repo.id)

    await db.commit()
    await db.refresh(repo)
    return await _serialize(db, repo)


@router.post("/github/sync")
async def sync_all(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Pull every active repo at once.

    This is the fallback when webhooks can't reach the server — on localhost,
    behind a firewall, or when a delivery failed. Safe to call often: the
    upsert is keyed on (tenant, repo, issue number), so re-importing the same
    issue updates the existing task instead of duplicating it.
    """
    repos = (
        await db.execute(
            select(GitHubRepo).where(
                GitHubRepo.tenant_id == tenant.id,
                GitHubRepo.is_active.is_(True),
            )
        )
    ).scalars().all()

    results = [await github_service.sync_repo(db, repo) for repo in repos]
    return {
        "repos": len(results),
        "synced": sum(r.get("synced", 0) for r in results if r.get("ok")),
        "results": results,
    }


@router.post("/github/repos/{repo_id}/sync")
async def sync_now(
    repo_id: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Manual reconcile, for when you don't want to wait for the interval."""
    repo = (
        await db.execute(
            select(GitHubRepo).where(GitHubRepo.id == repo_id, GitHubRepo.tenant_id == tenant.id)
        )
    ).scalars().first()
    if not repo:
        raise HTTPException(404, "Repository not configured")
    return await github_service.sync_repo(db, repo)


@router.get("/github/repos/{repo_id}/write-access")
async def write_access(
    repo_id: int,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Report whether this repo's token can actually create and edit issues.

    Checked up front so a missing scope surfaces here rather than as a failed
    push after someone has already written the task.
    """
    repo = (
        await db.execute(
            select(GitHubRepo).where(GitHubRepo.id == repo_id, GitHubRepo.tenant_id == tenant.id)
        )
    ).scalars().first()
    if not repo:
        raise HTTPException(404, "Repository not configured")

    token = crypto.decrypt(repo.token_encrypted) if repo.token_encrypted else None
    return await github_service.check_write_access(repo.full_name, token)


# ─── GitHub username mapping ──────────────────────────────────────────────────

@router.get("/github/user-mapping")
async def list_user_mapping(
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    App users alongside their GitHub logins.

    GitHub can't resolve our users, so assignment mirroring needs this mapping
    entered by hand. Users without one still get the issue — just unassigned.
    """
    rows = (
        await db.execute(
            select(User.id, User.name, User.email, User.role, User.github_username)
            .where(User.tenant_id == tenant.id, User.is_active.is_(True))
            .order_by(User.name)
        )
    ).all()
    return [
        {"id": r[0], "name": r[1], "email": r[2], "role": r[3], "github_username": r[4]}
        for r in rows
    ]


@router.put("/github/user-mapping/{user_id}")
async def set_user_mapping(
    user_id: int,
    data: GitHubUsernameUpdate,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant.id)
        )
    ).scalars().first()
    if not user:
        raise HTTPException(404, "User not found in this organisation")

    username = (data.github_username or "").strip().lstrip("@")
    user.github_username = username or None
    await db.commit()
    return {"id": user.id, "name": user.name, "github_username": user.github_username}


@router.delete("/github/repos/{repo_id}")
async def remove_repo(
    repo_id: int,
    delete_tasks: bool = False,
    tenant: Tenant = Depends(verify_tenant_api_key),
    db: AsyncSession = Depends(get_db),
):
    repo = (
        await db.execute(
            select(GitHubRepo).where(GitHubRepo.id == repo_id, GitHubRepo.tenant_id == tenant.id)
        )
    ).scalars().first()
    if not repo:
        raise HTTPException(404, "Repository not configured")

    removed = 0
    if delete_tasks:
        tasks = (
            await db.execute(
                select(Task).where(
                    Task.tenant_id == tenant.id, Task.github_repo == repo.full_name
                )
            )
        ).scalars().all()
        for t in tasks:
            await db.delete(t)
        removed = len(tasks)

    await db.delete(repo)
    await db.commit()
    return {
        "message": "Repository removed",
        "tasks_deleted": removed,
        "note": None if delete_tasks else "Mirrored tasks were kept and are now orphaned.",
    }
