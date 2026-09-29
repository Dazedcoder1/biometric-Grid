"""
Sharing, re-sharing, temporary access and cascade revocation.

The rule that matters most is in `grant`: **a share can never exceed what the
grantor holds**. Without that check, anyone given `view` could re-share at
`manage` and hand themselves full control of a credential they cannot even
read. Every other guard in the system is downstream of this one.

Tree shape: `parent_share_id` is the source of truth, `path` is a materialised
string written once at insert. Nothing ever moves — revoking changes `status`,
not the tree — so the path costs nothing to maintain and turns cascade
revocation into a single indexed UPDATE.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.models.credentials import Credential, Share, Team, TeamMember
from app.models.domain import User
from app.services.vault_service import LEVELS, _RANK, effective_level


async def grant(
    db: AsyncSession,
    *,
    ctx,
    credential: Credential,
    permission: str,
    grantee_user_id: int | None = None,
    grantee_team_id: int | None = None,
    starts_at: datetime | None = None,
    expires_at: datetime | None = None,
    parent_share_id: int | None = None,
) -> Share:
    """
    Share a credential, or re-share one already shared with you.

    Refuses, in this order:
      - a level the grantor does not hold (escalation)
      - re-sharing without `reshare`
      - a grantee outside the tenant
      - sharing with yourself
      - an expiry in the past
    """
    if permission not in LEVELS:
        raise HTTPException(400, f"Unknown permission {permission!r}.")

    if (grantee_user_id is None) == (grantee_team_id is None):
        raise HTTPException(400, "Share with exactly one user or one team.")

    own_level = await effective_level(
        db, user=ctx.user, credential=credential,
        grants_all=ctx.permissions.grants_all,
    )
    if own_level is None:
        raise HTTPException(404, "Credential not found.")

    # ── escalation ───────────────────────────────────────────────────────────
    # The check this module exists for. Granting above your own level would let
    # a `view` holder promote themselves to `manage` through a second account.
    if _RANK[permission] > _RANK[own_level]:
        await audit.record(
            db,
            action="share.escalation_blocked",
            result="denied",
            reason=f"tried to grant '{permission}' while holding '{own_level}'",
            target_type="credential",
            target_id=credential.id,
            details={"attempted": permission, "held": own_level},
            **ctx.audit_kwargs(),
        )
        raise HTTPException(
            403,
            f"You hold '{own_level}' on this credential and cannot grant "
            f"'{permission}'. A share can never exceed your own access.",
        )

    # ── re-share rights ──────────────────────────────────────────────────────
    # Owners and `manage` holders share by right. Anyone else needs `reshare`
    # explicitly, and must attach the new share to the one they received so the
    # tree records who it came through.
    is_owner = credential.owner_id == ctx.user.id or ctx.permissions.grants_all
    if not is_owner and _RANK[own_level] < _RANK["reshare"]:
        raise HTTPException(403, "You do not have permission to share this credential.")

    parent: Share | None = None
    if parent_share_id is not None:
        parent = (
            await db.execute(
                select(Share).where(
                    Share.id == parent_share_id,
                    Share.credential_id == credential.id,
                    Share.status == "active",
                )
            )
        ).scalars().first()
        if not parent:
            raise HTTPException(404, "The share you are re-sharing from is not active.")
        if _RANK[permission] > _RANK[parent.permission]:
            raise HTTPException(
                403, "A re-share cannot exceed the share it derives from."
            )

    # ── grantee validation ───────────────────────────────────────────────────
    if grantee_user_id is not None:
        if grantee_user_id == ctx.user.id:
            raise HTTPException(400, "You already have access to this credential.")
        grantee = (
            await db.execute(
                select(User).where(
                    User.id == grantee_user_id,
                    User.tenant_id == credential.tenant_id,
                    User.is_active.is_(True),
                )
            )
        ).scalars().first()
        if not grantee:
            # Same tenant only. Cross-tenant sharing is not a feature; a request
            # naming another tenant's user is either a bug or an attempt.
            raise HTTPException(404, "No such active user in this organisation.")
    else:
        team = (
            await db.execute(
                select(Team).where(
                    Team.id == grantee_team_id, Team.tenant_id == credential.tenant_id
                )
            )
        ).scalars().first()
        if not team:
            raise HTTPException(404, "No such team in this organisation.")

    now = datetime.now(timezone.utc)
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(400, "The expiry time is already in the past.")

    if starts_at is not None and starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)

    # A future start means the grant exists but is not yet usable — 'pending'
    # rather than 'active', so the access queries can filter on status alone.
    status = "pending" if (starts_at and starts_at > now) else "active"

    share = Share(
        tenant_id=credential.tenant_id,
        credential_id=credential.id,
        parent_share_id=parent.id if parent else None,
        path="",  # set below; the id is needed first
        grantor_id=ctx.user.id,
        grantee_user_id=grantee_user_id,
        grantee_team_id=grantee_team_id,
        permission=permission,
        starts_at=starts_at,
        expires_at=expires_at,
        status=status,
    )
    db.add(share)
    await db.flush()

    share.path = f"{parent.path if parent else '/'}{share.id}/"

    await audit.record(
        db,
        action="share.granted",
        target_type="credential",
        target_id=credential.id,
        details={
            "share_id": share.id,
            "permission": permission,
            "grantee_user_id": grantee_user_id,
            "grantee_team_id": grantee_team_id,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "via_share_id": parent.id if parent else None,
        },
        **ctx.audit_kwargs(),
    )
    return share


async def revoke(
    db: AsyncSession, *, ctx, share: Share, reason: str | None = None
) -> list[Share]:
    """
    Revoke a share and everything granted through it.

    Cascade is the approved behaviour, and the only one where "revoke" means
    revoke. Rows are never deleted — a revoked share is evidence that access
    existed and was withdrawn.

    Returns every share affected, the named one first.
    """
    if share.status in ("revoked", "expired"):
        raise HTTPException(409, f"This share is already {share.status}.")

    credential = (
        await db.execute(select(Credential).where(Credential.id == share.credential_id))
    ).scalars().first()
    if not credential:
        raise HTTPException(404, "Credential not found.")

    # You may revoke a share you granted, or any share if you manage the
    # credential. Otherwise someone could revoke a colleague's access to
    # something they merely have a share on.
    own_level = await effective_level(
        db, user=ctx.user, credential=credential,
        grants_all=ctx.permissions.grants_all,
    )
    may_revoke = (
        share.grantor_id == ctx.user.id
        or credential.owner_id == ctx.user.id
        or ctx.permissions.grants_all
        or (own_level is not None and _RANK[own_level] >= _RANK["manage"])
    )
    if not may_revoke:
        raise HTTPException(403, "You cannot revoke this share.")

    now = datetime.now(timezone.utc)

    # One indexed statement for the whole subtree. The path index uses
    # text_pattern_ops, without which this silently becomes a sequential scan.
    subtree = (
        await db.execute(
            select(Share).where(
                Share.path.like(f"{share.path}%"),
                Share.status.in_(("active", "pending")),
            )
        )
    ).scalars().all()

    for row in subtree:
        row.status = "revoked"
        row.revoked_at = now
        row.revoked_by = ctx.user.id
        row.revoked_reason = (
            reason if row.id == share.id
            else f"cascade from share {share.id}"
        )

    # One audit entry per affected share, so the log shows a deliberate act and
    # its consequences rather than N unexplained revocations.
    for row in subtree:
        await audit.record(
            db,
            action="share.revoked",
            target_type="credential",
            target_id=share.credential_id,
            reason=row.revoked_reason,
            details={
                "share_id": row.id,
                "cascaded": row.id != share.id,
                "root_share_id": share.id,
                "grantee_user_id": row.grantee_user_id,
                "grantee_team_id": row.grantee_team_id,
            },
            **ctx.audit_kwargs(),
        )

    return sorted(subtree, key=lambda s: (s.id != share.id, s.id))


async def descendants(db: AsyncSession, share: Share) -> list[Share]:
    """Everything granted through this share, at any depth. Excludes itself."""
    rows = (
        await db.execute(
            select(Share).where(Share.path.like(f"{share.path}%"), Share.id != share.id)
        )
    ).scalars().all()
    return list(rows)


async def tree_for_credential(db: AsyncSession, credential_id: int) -> list[dict]:
    """
    The whole sharing tree, flat, with depth — the shape a UI needs to render
    an indented list or a graph.

    Ordering by path gives depth-first order for free: '/1/' sorts before
    '/1/4/', which sorts before '/2/'.
    """
    rows = (
        await db.execute(
            select(Share).where(Share.credential_id == credential_id).order_by(Share.path)
        )
    ).scalars().all()

    return [
        {
            "id": s.id,
            "parent_share_id": s.parent_share_id,
            "depth": max(0, s.path.count("/") - 2),
            "permission": s.permission,
            "status": s.status,
            "grantor_id": s.grantor_id,
            "grantee_user_id": s.grantee_user_id,
            "grantee_team_id": s.grantee_team_id,
            "starts_at": s.starts_at,
            "expires_at": s.expires_at,
            "revoked_at": s.revoked_at,
            "revoked_reason": s.revoked_reason,
            "created_at": s.created_at,
        }
        for s in rows
    ]


async def shared_with_me(db: AsyncSession, *, user: User) -> list[dict]:
    """
    The Shared Vault: credentials reaching this user through an active share,
    with the owner and the path they arrived by.
    """
    now = datetime.now(timezone.utc)
    team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)

    rows = (
        await db.execute(
            select(Share, Credential)
            .join(Credential, Credential.id == Share.credential_id)
            .where(
                Share.status == "active",
                Credential.deleted_at.is_(None),
                or_(
                    Share.grantee_user_id == user.id,
                    Share.grantee_team_id.in_(team_ids),
                ),
                or_(Share.starts_at.is_(None), Share.starts_at <= now),
                or_(Share.expires_at.is_(None), Share.expires_at > now),
            )
            .order_by(Credential.name)
        )
    ).all()

    return [
        {
            "credential_id": c.id,
            "name": c.name,
            "username": c.username,
            "url": c.url,
            "kind": c.kind,
            "owner_id": c.owner_id,
            "share_id": s.id,
            "permission": s.permission,
            "expires_at": s.expires_at,
            "granted_by": s.grantor_id,
            # How many hands it passed through before reaching you.
            "hops": max(0, s.path.count("/") - 2),
        }
        for s, c in rows
    ]


async def expire_due(db: AsyncSession) -> int:
    """
    Mark every share whose expiry has passed, and cascade to its subtree.

    Run by the background sweeper. Expiry is enforced at read time too — the
    access queries all filter on `expires_at` — so a late sweep never grants
    access it should not. The sweep exists to make the state visible and to put
    "access expired" in the audit log at roughly the right moment.
    """
    now = datetime.now(timezone.utc)

    due = (
        await db.execute(
            select(Share).where(
                Share.status.in_(("active", "pending")),
                Share.expires_at.is_not(None),
                Share.expires_at <= now,
            )
        )
    ).scalars().all()

    if not due:
        # Separately: activate anything whose start time has arrived.
        await _activate_due(db, now)
        return 0

    affected: dict[int, Share] = {}
    for root in due:
        subtree = (
            await db.execute(
                select(Share).where(
                    Share.path.like(f"{root.path}%"),
                    Share.status.in_(("active", "pending")),
                )
            )
        ).scalars().all()
        for row in subtree:
            affected[row.id] = row

    for row in affected.values():
        row.status = "expired"
        row.revoked_at = now
        row.revoked_reason = "access expired"

    for row in affected.values():
        await audit.record(
            db,
            action="share.expired",
            actor_id=None,          # the system, not a person
            actor_role="system",
            tenant_id=row.tenant_id,
            target_type="credential",
            target_id=row.credential_id,
            reason="access expired",
            details={"share_id": row.id, "grantee_user_id": row.grantee_user_id},
        )

    await _activate_due(db, now)
    return len(affected)


async def _activate_due(db: AsyncSession, now: datetime) -> int:
    """Flip pending shares to active once their start time has passed."""
    result = await db.execute(
        update(Share)
        .where(
            Share.status == "pending",
            Share.starts_at.is_not(None),
            Share.starts_at <= now,
            or_(Share.expires_at.is_(None), Share.expires_at > now),
        )
        .values(status="active")
    )
    return result.rowcount or 0
