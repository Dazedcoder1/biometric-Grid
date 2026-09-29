"""
Authorisation guards.

Deny-by-default in practice: a route with no guard is unreachable by policy
(reviewers reject it), and a guard whose permission code is misspelled denies
rather than grants, because PermissionSet.has() returns False for unknown
codes. Failing closed on a typo is the whole point.

Usage:

    @router.post("/credentials")
    async def create(_=Depends(require_permission("credential.create"))): ...

    @router.post("/credentials/{id}/reveal")
    async def reveal(ctx=Depends(require_step_up("credential.reveal"))): ...

Separate from app/api/dependencies.py, which holds the pre-existing legacy
guards. Those still work and are untouched.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core import audit, mfa
from app.core.security import decode_token
from app.core.permissions import DENY_ALL, STEP_UP_REQUIRED, PermissionSet
from app.db.session import get_db
from app.models.domain import User
from app.models.security import Permission, Role, RolePermission, UserRole

logger = logging.getLogger(__name__)


class SecurityContext:
    """Everything a guarded route needs to authorise and audit one request."""

    __slots__ = ("user", "permissions", "session_jti", "source_ip", "user_agent")

    def __init__(
        self,
        user: User,
        permissions: PermissionSet,
        *,
        session_jti: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.user = user
        self.permissions = permissions
        self.session_jti = session_jti
        self.source_ip = source_ip
        self.user_agent = user_agent

    @property
    def tenant_id(self) -> int | None:
        return self.user.tenant_id

    def audit_kwargs(self) -> dict:
        """Actor fields for audit.record(), so every call site is consistent."""
        return {
            "tenant_id": self.user.tenant_id,
            "actor_id": self.user.id,
            "actor_role": self.user.role,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "session_jti": self.session_jti,
        }


def _client_ip(request: Request) -> str | None:
    """
    Caller's IP, honouring one hop of X-Forwarded-For.

    Only the *last* entry is trustworthy and only because our own proxy appends
    it; earlier entries are client-supplied and forgeable. Recorded for audit,
    never used for authorisation.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else None


async def load_permissions(db: AsyncSession, user: User) -> PermissionSet:
    """
    Resolve a user's effective permissions.

    Union of every unexpired role. Empty union means no access at all, which is
    deny-by-default arriving as a consequence of the data rather than a special
    case in the code.
    """
    now = datetime.now(UTC)

    rows = (
        await db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user.id,
                (UserRole.expires_at.is_(None)) | (UserRole.expires_at > now),
            )
        )
    ).scalars().all()

    if not rows:
        # No explicit assignment. Fall back to the legacy users.role string so
        # existing accounts keep working — see models/security.py. This bridge
        # disappears once every user has a row in user_roles.
        legacy = (
            await db.execute(
                select(Role).where(Role.code == user.role, Role.tenant_id.is_(None))
            )
        ).scalars().first()
        rows = [legacy] if legacy else []

    if not rows:
        return DENY_ALL

    if any(r.grants_all for r in rows):
        return PermissionSet(grants_all=True, role_codes=[r.code for r in rows])

    role_ids = [r.id for r in rows]
    codes = (
        await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(role_ids))
        )
    ).scalars().all()

    return PermissionSet(codes, role_codes=[r.code for r in rows])


def _session_jti(request: Request) -> str | None:
    """
    The current access token's jti, used to bind step-up assertions to one
    session.

    Read straight from the Authorization header rather than from request.state:
    nothing populates request.state, so the earlier version silently returned
    None — which made the session check in mfa.consume_assertion inert, because
    it only fires when both sides have a value. An assertion obtained in one
    session would then have authorised a reveal in another, including a session
    opened with a stolen refresh token.

    Not re-verified here: get_current_user has already decoded and validated
    this exact token, so a forged one never reaches this point.
    """
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    payload = decode_token(header.split(" ", 1)[1].strip())
    return payload.get("jti") if payload else None


async def get_security_context(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SecurityContext:
    """Authenticated caller plus resolved permissions. No authorisation yet."""
    permissions = await load_permissions(db, user)
    return SecurityContext(
        user,
        permissions,
        session_jti=_session_jti(request),
        source_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def require_permission(code: str):
    """
    Guard requiring one permission. Denials are audited before the 403.

    A denied attempt is more interesting than a successful one — it is what
    probing looks like — so it is never silently dropped.
    """

    async def guard(
        ctx: SecurityContext = Depends(get_security_context),
        db: AsyncSession = Depends(get_db),
    ) -> SecurityContext:
        if ctx.permissions.has(code):
            return ctx

        await audit.record(
            db,
            action="authz.denied",
            result="denied",
            reason=f"missing permission: {code}",
            details={"required": code, "roles": list(ctx.permissions.role_codes)},
            **ctx.audit_kwargs(),
        )
        await db.commit()

        # Says which permission is missing. That is a deliberate trade: it helps
        # legitimate users and administrators far more than it helps an
        # attacker, who already knows what they attempted.
        raise HTTPException(403, f"This action requires the '{code}' permission.")

    return guard


def require_step_up(code: str, *, single_use: bool = False):
    """
    Guard requiring the permission *and* a fresh MFA assertion.

    The token arrives in `X-Step-Up-Token`, not the body — it applies to the
    request rather than the payload, and keeping it out of the body means it
    never lands in a JSON log.

    Callers without a token get 401 with `X-Step-Up-Required`, which the
    frontend uses to open the code prompt and retry.
    """

    async def guard(
        ctx: SecurityContext = Depends(get_security_context),
        db: AsyncSession = Depends(get_db),
        x_step_up_token: str | None = Header(None, alias="X-Step-Up-Token"),
    ) -> SecurityContext:
        if not ctx.permissions.has(code):
            await audit.record(
                db,
                action="authz.denied",
                result="denied",
                reason=f"missing permission: {code}",
                details={"required": code},
                **ctx.audit_kwargs(),
            )
            await db.commit()
            raise HTTPException(403, f"This action requires the '{code}' permission.")

        # Belt and braces: the catalogue says this code needs step-up, so a
        # future edit that removes the flag cannot silently disable the gate
        # without also removing this guard.
        if code not in STEP_UP_REQUIRED:
            logger.warning(
                "require_step_up used for %s, which is not marked requires_step_up", code
            )

        if not x_step_up_token:
            await audit.record(
                db,
                action="mfa.step_up_required",
                result="denied",
                reason="no step-up token supplied",
                details={"required": code},
                **ctx.audit_kwargs(),
            )
            await db.commit()
            raise HTTPException(
                401,
                "Re-authentication required for this action.",
                headers={"X-Step-Up-Required": code},
            )

        try:
            await mfa.consume_assertion(
                db,
                token=x_step_up_token,
                user_id=ctx.user.id,
                purpose=code,
                session_jti=ctx.session_jti,
                single_use=single_use,
            )
        except mfa.MfaError as exc:
            await audit.record(
                db,
                action="mfa.step_up_rejected",
                result="denied",
                reason=str(exc),
                details={"required": code},
                **ctx.audit_kwargs(),
            )
            await db.commit()
            raise HTTPException(
                401, str(exc), headers={"X-Step-Up-Required": code}
            ) from exc

        return ctx

    return guard


def require_any_permission(*codes: str):
    """Guard satisfied by any one of several permissions."""

    async def guard(
        ctx: SecurityContext = Depends(get_security_context),
        db: AsyncSession = Depends(get_db),
    ) -> SecurityContext:
        if ctx.permissions.has_any(*codes):
            return ctx

        await audit.record(
            db,
            action="authz.denied",
            result="denied",
            reason=f"missing all of: {', '.join(codes)}",
            details={"required_any": list(codes)},
            **ctx.audit_kwargs(),
        )
        await db.commit()
        raise HTTPException(403, f"This action requires one of: {', '.join(codes)}.")

    return guard
