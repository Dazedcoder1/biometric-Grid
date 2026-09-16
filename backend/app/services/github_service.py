"""
GitHub issue mirroring.

Read-only by design: issues flow GitHub -> tasks, and nothing this module does
writes back to a repository. Tokens therefore only ever need `repo` read scope.

Two paths keep tasks current:
  1. Webhooks — GitHub POSTs issue events, we upsert immediately.
  2. Reconcile — a slow background pass that re-pulls each repo, catching
     anything a missed or failed delivery left stale.

Both funnel through upsert_issue(), which is idempotent on
(tenant_id, github_repo, github_issue_number).
"""

import asyncio
import hashlib
import hmac
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.core import crypto
from app.core.config import settings
from app.models.domain import GitHubRepo, Task, TaskPriority, TaskSource, TaskStatus

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)

# GitHub label -> our priority. Anything unmatched stays MEDIUM.
_PRIORITY_LABELS = {
    "urgent": TaskPriority.URGENT.value,
    "critical": TaskPriority.URGENT.value,
    "p0": TaskPriority.URGENT.value,
    "high": TaskPriority.HIGH.value,
    "p1": TaskPriority.HIGH.value,
    "low": TaskPriority.LOW.value,
    "p3": TaskPriority.LOW.value,
}


# ─── Webhook signature ────────────────────────────────────────────────────────

def verify_signature(payload_body: bytes, secret: str, signature_header: str | None) -> bool:
    """
    Validate GitHub's X-Hub-Signature-256 header.

    Compared with hmac.compare_digest so a wrong signature can't be recovered
    byte-by-byte from response timing.
    """
    if not signature_header or not secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ─── Mapping ──────────────────────────────────────────────────────────────────

def _priority_from_labels(labels: list[str]) -> str:
    for label in labels:
        hit = _PRIORITY_LABELS.get(label.lower().strip())
        if hit:
            return hit
    return TaskPriority.MEDIUM.value


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def upsert_issue(db, repo: GitHubRepo, issue: dict) -> Task | None:
    """
    Create or update the Task mirroring one GitHub issue.

    Returns None for pull requests — the issues API returns those too, and they
    are not tasks. Caller commits.
    """
    if issue.get("pull_request"):
        return None

    number = issue.get("number")
    if number is None:
        return None

    labels = [lbl.get("name", "") for lbl in issue.get("labels", []) if isinstance(lbl, dict)]

    # Respect the repo's label filter, if one is configured.
    if repo.label_filter:
        wanted = {l.strip().lower() for l in repo.label_filter.split(",") if l.strip()}
        if wanted and not wanted.intersection({l.lower() for l in labels}):
            return None

    existing = (
        await db.execute(
            select(Task).where(
                Task.tenant_id == repo.tenant_id,
                Task.github_repo == repo.full_name,
                Task.github_issue_number == number,
            )
        )
    ).scalars().first()

    gh_state = issue.get("state")
    body = issue.get("body") or ""

    if existing is None:
        task = Task(
            tenant_id=repo.tenant_id,
            title=issue.get("title") or f"Issue #{number}",
            description=body,
            source=TaskSource.GITHUB.value,
            status=TaskStatus.DONE.value if gh_state == "closed" else TaskStatus.TODO.value,
            priority=_priority_from_labels(labels),
            github_repo_id=repo.id,
            github_repo=repo.full_name,
            github_issue_number=number,
            github_url=issue.get("html_url"),
            github_state=gh_state,
            github_labels=",".join(labels) or None,
            github_updated_at=_parse_ts(issue.get("updated_at")),
        )
        db.add(task)
        return task

    # Update the mirrored fields only. Assignment, due date and local status
    # are owned by the app, so a resync must not clobber them — the one
    # exception is closing, which is unambiguous.
    existing.title = issue.get("title") or existing.title
    existing.description = body
    existing.github_url = issue.get("html_url") or existing.github_url
    existing.github_labels = ",".join(labels) or None
    existing.github_updated_at = _parse_ts(issue.get("updated_at"))
    existing.github_repo_id = repo.id

    if gh_state != existing.github_state:
        existing.github_state = gh_state
        if gh_state == "closed":
            existing.status = TaskStatus.DONE.value
            existing.completed_at = datetime.now(timezone.utc)
        elif existing.status == TaskStatus.DONE.value:
            # Reopened upstream — pull it back into the board.
            existing.status = TaskStatus.TODO.value
            existing.completed_at = None

    return existing


# ─── Fetching ─────────────────────────────────────────────────────────────────

async def fetch_issues(repo: GitHubRepo, per_page: int = 100) -> list[dict]:
    """
    Pull recent issues for one repo, newest-updated first.

    Bounded by GITHUB_SYNC_PAGE_LIMIT so a repo with thousands of issues can't
    burn the whole rate limit in a single pass.
    """
    token = crypto.decrypt(repo.token_encrypted) if repo.token_encrypted else None

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gridsphere-task-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    collected: list[dict] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for page in range(1, max(1, settings.GITHUB_SYNC_PAGE_LIMIT) + 1):
            resp = await client.get(
                f"{GITHUB_API}/repos/{repo.full_name}/issues",
                headers=headers,
                params={
                    "state": "all",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page,
                },
            )
            if resp.status_code == 401:
                raise PermissionError("GitHub rejected the token (401). Check it hasn't expired.")
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                raise RuntimeError("GitHub rate limit reached. Add a token or sync less often.")
            if resp.status_code == 404:
                raise FileNotFoundError(
                    f"Repo '{repo.full_name}' not found, or the token lacks access to it."
                )
            resp.raise_for_status()

            batch = resp.json()
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < per_page:
                break

    return collected


async def sync_repo(db, repo: GitHubRepo) -> dict:
    """Reconcile one repo. Records the outcome on the repo row either way."""
    try:
        issues = await fetch_issues(repo)
    except Exception as exc:
        repo.last_sync_error = str(exc)[:500]
        await db.commit()
        logger.warning("GitHub sync failed for %s: %s", repo.full_name, exc)
        return {"repo": repo.full_name, "ok": False, "error": str(exc)}

    synced = 0
    for issue in issues:
        if await upsert_issue(db, repo, issue) is not None:
            synced += 1

    repo.last_synced_at = datetime.now(timezone.utc)
    repo.last_sync_error = None
    await db.commit()
    return {"repo": repo.full_name, "ok": True, "synced": synced}


# ─── Writing (app -> GitHub) ──────────────────────────────────────────────────
#
# Every write goes through _write(), which returns (ok, payload_or_error)
# instead of raising. Callers must never let a GitHub failure roll back the
# local task — the task is the source of truth for the app, and GitHub is a
# mirror that can be reconciled later.

class GitHubWriteError(Exception):
    pass


def _headers(token: str | None) -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gridsphere-task-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _repo_token(repo: GitHubRepo) -> str | None:
    return crypto.decrypt(repo.token_encrypted) if repo.token_encrypted else None


async def _write(method: str, url: str, token: str | None, json_body: dict) -> tuple[bool, dict]:
    if not token:
        return False, {"error": "No token configured for this repository — writes need one."}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(method, url, headers=_headers(token), json=json_body)
    except httpx.HTTPError as exc:
        return False, {"error": f"Could not reach GitHub: {exc}"}

    if resp.status_code in (200, 201):
        return True, resp.json()
    if resp.status_code == 403:
        return False, {"error": "GitHub refused the write (403). The token likely lacks "
                                "issues:write / repo scope."}
    if resp.status_code == 404:
        return False, {"error": "Repo or issue not found, or the token can't see it."}
    if resp.status_code == 410:
        return False, {"error": "Issues are disabled on this repository."}
    return False, {"error": f"GitHub returned {resp.status_code}: {resp.text[:200]}"}


async def create_issue(repo: GitHubRepo, *, title: str, body: str | None = None,
                       labels: list[str] | None = None,
                       assignees: list[str] | None = None) -> tuple[bool, dict]:
    payload: dict = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees
    return await _write(
        "POST", f"{GITHUB_API}/repos/{repo.full_name}/issues", _repo_token(repo), payload
    )


async def update_issue(repo: GitHubRepo, number: int, **fields) -> tuple[bool, dict]:
    """fields may include title, body, state ('open'/'closed'), assignees, labels."""
    payload = {k: v for k, v in fields.items() if v is not None}
    if not payload:
        return True, {}
    return await _write(
        "PATCH", f"{GITHUB_API}/repos/{repo.full_name}/issues/{number}",
        _repo_token(repo), payload,
    )


async def create_issue_comment(repo: GitHubRepo, number: int, body: str) -> tuple[bool, dict]:
    return await _write(
        "POST", f"{GITHUB_API}/repos/{repo.full_name}/issues/{number}/comments",
        _repo_token(repo), {"body": body},
    )


async def check_write_access(full_name: str, token: str | None) -> dict:
    """
    Report whether a token can actually write issues, before the user relies on it.

    Classic PATs advertise their scopes in X-OAuth-Scopes. Fine-grained tokens
    don't, so we fall back to the repository's own `permissions.push` flag.
    """
    if not token:
        return {"can_write": False, "reason": "No token configured (public read only)."}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{GITHUB_API}/repos/{full_name}", headers=_headers(token))
    except httpx.HTTPError as exc:
        return {"can_write": False, "reason": f"Could not reach GitHub: {exc}"}

    if resp.status_code != 200:
        return {"can_write": False, "reason": f"GitHub returned {resp.status_code}."}

    scopes_header = resp.headers.get("X-OAuth-Scopes")
    if scopes_header is not None:
        scopes = {s.strip() for s in scopes_header.split(",") if s.strip()}
        if "repo" in scopes or "public_repo" in scopes:
            return {"can_write": True, "reason": f"Token scopes: {sorted(scopes)}"}
        return {
            "can_write": False,
            "reason": f"Token has scopes {sorted(scopes) or ['(none)']}; needs 'repo' "
                      "(or 'public_repo' for public repositories).",
        }

    # Fine-grained token: infer from the repo permissions it reports.
    perms = (resp.json() or {}).get("permissions") or {}
    if perms.get("push") or perms.get("maintain") or perms.get("admin"):
        return {"can_write": True, "reason": "Fine-grained token with write permission."}
    return {
        "can_write": False,
        "reason": "Fine-grained token without write permission on this repository. "
                  "Grant it Read and write access to Issues.",
    }


async def list_assignable_users(full_name: str, token: str | None) -> dict:
    """
    Who GitHub will actually accept as an assignee on this repository.

    This is `/assignees`, not `/collaborators`, and the difference matters:
    GitHub only permits assignment to users with push access, and it does not
    complain when you send it anyone else — the issue is created or patched
    successfully with the assignee silently dropped. So the only way to know an
    assignment will stick is to check it against this list first.

    Returns {"assignees": [{"login", "avatar_url", "html_url"}], "error": str|None}.
    An error is reported rather than raised: the mapping table is still usable
    by hand when GitHub is unreachable.
    """
    if not token:
        return {"assignees": [], "error": "No token configured for this repository."}

    collected: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Two pages is 200 people — far past any realistic team, and it
            # keeps a misconfigured org from stalling the page.
            for page in (1, 2):
                resp = await client.get(
                    f"{GITHUB_API}/repos/{full_name}/assignees",
                    headers=_headers(token),
                    params={"per_page": 100, "page": page},
                )
                if resp.status_code == 404:
                    return {"assignees": [],
                            "error": "Repository not found, or the token cannot see it."}
                if resp.status_code != 200:
                    return {"assignees": [],
                            "error": f"GitHub returned {resp.status_code}."}

                batch = resp.json() or []
                collected.extend(
                    {
                        "login": u.get("login"),
                        "avatar_url": u.get("avatar_url"),
                        "html_url": u.get("html_url"),
                    }
                    for u in batch
                    if u.get("login")
                )
                if len(batch) < 100:
                    break
    except httpx.HTTPError as exc:
        return {"assignees": [], "error": f"Could not reach GitHub: {exc}"}

    collected.sort(key=lambda u: (u["login"] or "").lower())
    return {"assignees": collected, "error": None}


async def verify_repo_access(full_name: str, token: str | None) -> dict:
    """Check a repo is reachable before saving its config, so errors surface early."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gridsphere-task-sync",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{GITHUB_API}/repos/{full_name}", headers=headers)

    if resp.status_code == 200:
        data = resp.json()
        return {
            "ok": True,
            "full_name": data.get("full_name"),
            "private": data.get("private"),
            "open_issues": data.get("open_issues_count"),
        }
    if resp.status_code == 401:
        return {"ok": False, "error": "Token rejected by GitHub (401)."}
    if resp.status_code == 404:
        return {"ok": False, "error": "Repo not found, or the token can't see it."}
    return {"ok": False, "error": f"GitHub returned {resp.status_code}."}


# ─── Background reconcile ─────────────────────────────────────────────────────

async def reconcile_loop():
    """
    Periodic catch-up pass over every active repo.

    Webhooks are the fast path; this exists because deliveries do get missed
    (endpoint down, transient 5xx, secret rotated). Runs until cancelled.
    """
    interval = settings.GITHUB_SYNC_INTERVAL_MINUTES
    if interval <= 0:
        logger.info("GitHub reconcile loop disabled (GITHUB_SYNC_INTERVAL_MINUTES=0)")
        return

    from app.db.session import AsyncSessionLocal

    # Let the app finish starting before the first pass.
    await asyncio.sleep(60)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                repos = (
                    await db.execute(select(GitHubRepo).where(GitHubRepo.is_active.is_(True)))
                ).scalars().all()
                for repo in repos:
                    await sync_repo(db, repo)
                if repos:
                    logger.info("GitHub reconcile pass complete (%d repos)", len(repos))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("GitHub reconcile pass failed; will retry next interval")

        await asyncio.sleep(interval * 60)
