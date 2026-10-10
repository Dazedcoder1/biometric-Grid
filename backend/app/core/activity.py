"""
Recording ordinary activity — sign-ins, people, leave, devices, settings — in
the same hash-chained audit log the vault uses.

The audit log used to hold vault activity and nothing else. Approving leave,
adding an employee, deleting a department or signing in left no trace, so the
log looked frozen to anyone not handling credentials. This is the one call
every other route uses to write to it.

    await activity.log(db, request, action="leave.approved", tenant_id=...,
                       target_type="leave", target_id=leave.leave_id,
                       details={"employee": name})
    await db.commit()

Same transaction as the change it describes: call it BEFORE the route's
commit, so the action and its record land together or not at all.

Who did it is read from the request rather than passed in, because most
Tenant Admin routes only know the organisation (verify_tenant_api_key returns
a Tenant, not a person):

    * a bearer token naming a real user in this organisation (or a Super
      Admin acting in it) -> that user;
    * an X-API-Key, or a token that names nobody real -> no person,
      actor_role "api_key". An API key carries an organisation, not a
      person, and the log says so rather than inventing someone.

Never pass passwords, tokens or keys in `details`. audit._scrub redacts keys
that look like secrets as a backstop; it is not permission to rely on it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.security import decode_token
from app.models.domain import User


def _client_ip(request: Request) -> str | None:
    # Same rule as deps_security._client_ip: only the last X-Forwarded-For hop
    # is ours. Recorded for the audit trail, never used to authorise.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else None


async def resolve_actor(
    db: AsyncSession, request: Request, tenant_id: int | None
) -> tuple[int | None, str | None, str | None]:
    """(actor_id, actor_role, session_jti) for this request."""
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        payload = decode_token(header.split(" ", 1)[1].strip()) or {}
        uid = payload.get("user_id")
        if uid is not None:
            user = (await db.execute(select(User).where(User.id == uid))).scalars().first()
            # A token from /tenant-login carries the tenant id in user_id —
            # it names no person. Only accept a real user of this organisation,
            # or a Super Admin acting inside it.
            if user and (user.tenant_id == tenant_id or user.role == "super_admin"):
                return user.id, user.role, payload.get("jti")
    if request.headers.get("x-api-key") or header:
        return None, "api_key", None
    return None, None, None


async def log(
    db: AsyncSession,
    request: Request,
    *,
    action: str,
    tenant_id: int | None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: Mapping[str, Any] | None = None,
    result: str = "success",
    reason: str | None = None,
    actor: User | None = None,
    anonymous: str | None = None,
) -> None:
    """
    Append one entry. Does not commit — the route does, with its own change.

    Pass `actor` when the route already has the signed-in user; otherwise it
    is worked out from the request. Pass `anonymous` ("api_key", "unknown")
    for entries with no person behind them at all — a failed sign-in, a
    sign-in by API key — so the request is not searched for one.
    """
    if anonymous is not None:
        actor_id, actor_role, jti = None, anonymous, None
    elif actor is not None:
        actor_id, actor_role = actor.id, actor.role
        header = request.headers.get("authorization") or ""
        payload = (
            decode_token(header.split(" ", 1)[1].strip())
            if header.lower().startswith("bearer ") else None
        ) or {}
        jti = payload.get("jti")
    else:
        actor_id, actor_role, jti = await resolve_actor(db, request, tenant_id)

    await audit.record(
        db,
        action=action,
        result=result,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        details=dict(details) if details else None,
        source_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        session_jti=jti,
    )
