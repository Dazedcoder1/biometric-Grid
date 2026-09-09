"""
GitHub webhook receiver.

This is the one unauthenticated endpoint in the app, so every request must
prove itself with an HMAC signature before we touch the database.

Repo -> tenant resolution comes from the payload's repository.full_name. When
several tenants mirror the same repo, each candidate is checked against its own
webhook secret, and only those whose secret validates receive the update.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core import crypto
from app.db.session import get_db
from app.models.domain import GitHubRepo, Task, TaskComment
from app.services import github_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Events that change an issue's content or state.
_RELEVANT_ACTIONS = {
    "opened", "edited", "closed", "reopened",
    "labeled", "unlabeled", "assigned", "unassigned",
}


@router.post("/github")
async def receive_github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Body is not valid JSON")

    # GitHub sends this once when you create the hook.
    if x_github_event == "ping":
        return {"message": "pong"}

    if x_github_event not in ("issues", "issue_comment"):
        return {"message": f"Ignoring '{x_github_event}' event"}

    repo_full_name = (payload.get("repository") or {}).get("full_name")
    if not repo_full_name:
        raise HTTPException(400, "Payload has no repository.full_name")

    candidates = (
        await db.execute(
            select(GitHubRepo).where(
                GitHubRepo.full_name == repo_full_name,
                GitHubRepo.is_active.is_(True),
            )
        )
    ).scalars().all()

    if not candidates:
        # Don't confirm or deny which repos are configured.
        logger.info("Webhook for unconfigured repo %s", repo_full_name)
        return {"message": "No active configuration for this repository"}

    # Only tenants whose stored secret matches this signature get the update.
    authorised = [
        repo for repo in candidates
        if github_service.verify_signature(
            raw_body,
            crypto.decrypt(repo.webhook_secret_encrypted) or "",
            x_hub_signature_256,
        )
    ]

    if not authorised:
        logger.warning("Rejected webhook for %s: bad signature", repo_full_name)
        raise HTTPException(401, "Invalid signature")

    action = payload.get("action")
    issue = payload.get("issue")
    if not issue:
        return {"message": "No issue in payload"}

    # ─── Comments made on the issue, mirrored inward ──────────────────────────
    if x_github_event == "issue_comment":
        if action not in ("created", "edited"):
            return {"message": f"Ignoring comment action '{action}'"}

        gh_comment = payload.get("comment") or {}
        gh_id = gh_comment.get("id")
        if not gh_id:
            return {"message": "No comment id in payload"}

        imported = 0
        for repo in authorised:
            task = (
                await db.execute(
                    select(Task).where(
                        Task.tenant_id == repo.tenant_id,
                        Task.github_repo == repo.full_name,
                        Task.github_issue_number == issue.get("number"),
                    )
                )
            ).scalars().first()
            if task is None:
                continue

            # This is the echo guard. A comment we posted was written back with
            # its GitHub id, so when GitHub tells us about it we recognise it
            # and skip, instead of importing our own words as a new comment.
            already = (
                await db.execute(
                    select(TaskComment).where(
                        TaskComment.task_id == task.id,
                        TaskComment.github_comment_id == gh_id,
                    )
                )
            ).scalars().first()
            if already is not None:
                continue

            author = (gh_comment.get("user") or {}).get("login") or "GitHub user"
            db.add(TaskComment(
                task_id=task.id,
                user_id=None,                      # no app user behind it
                author_name=f"{author} (GitHub)",
                body=gh_comment.get("body") or "",
                github_comment_id=gh_id,
            ))
            imported += 1

        await db.commit()
        return {
            "message": "Processed",
            "repository": repo_full_name,
            "action": action,
            "comments_imported": imported,
        }

    # ─── Issue events ─────────────────────────────────────────────────────────
    if action not in _RELEVANT_ACTIONS:
        return {"message": f"Ignoring action '{action}'"}

    updated = 0
    for repo in authorised:
        task = await github_service.upsert_issue(db, repo, issue)
        if task is not None:
            updated += 1
    await db.commit()

    return {
        "message": "Processed",
        "repository": repo_full_name,
        "action": action,
        "tasks_updated": updated,
    }
