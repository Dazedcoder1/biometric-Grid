"""Sharing routes: grant, revoke, inspect the tree, and the Shared Vault."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import (
    SecurityContext,
    get_security_context,
    require_permission,
)
from app.db.session import get_db
from app.models.credentials import Share
from app.services import share_service as shares
from app.services import vault_service as svc

router = APIRouter()


class ShareIn(BaseModel):
    permission: str = Field(..., description="view | reveal | edit | reshare | manage")
    grantee_user_id: int | None = None
    grantee_team_id: int | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    # Set when re-sharing something shared with you: records who it came
    # through, and caps the new share at that share's level.
    parent_share_id: int | None = None


class RevokeIn(BaseModel):
    reason: str | None = Field(None, max_length=500)


@router.get("/shared-with-me")
async def shared_with_me(
    ctx: SecurityContext = Depends(require_permission("vault.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    The Shared Vault. Computed from active shares rather than stored, so it can
    never disagree with the grants it represents.
    """
    return await shares.shared_with_me(db, user=ctx.user)


@router.get("/credentials/{credential_id}/shares")
async def credential_shares(
    credential_id: int,
    ctx: SecurityContext = Depends(require_permission("share.view")),
    db: AsyncSession = Depends(get_db),
):
    """The sharing tree, flat with depth — who shared to whom, via whom."""
    credential = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="view",
        grants_all=ctx.permissions.grants_all,
    )
    return await shares.tree_for_credential(db, credential_id)


@router.post("/credentials/{credential_id}/shares", status_code=201)
async def create_share(
    credential_id: int,
    data: ShareIn,
    ctx: SecurityContext = Depends(require_permission("share.grant")),
    db: AsyncSession = Depends(get_db),
):
    """
    Share, or re-share. The level is capped at what you hold — see
    share_service.grant, which audits a blocked escalation before refusing.
    """
    credential = await svc.get_credential(db, credential_id)

    share = await shares.grant(
        db,
        ctx=ctx,
        credential=credential,
        permission=data.permission,
        grantee_user_id=data.grantee_user_id,
        grantee_team_id=data.grantee_team_id,
        starts_at=data.starts_at,
        expires_at=data.expires_at,
        parent_share_id=data.parent_share_id,
    )
    await db.commit()

    return {
        "id": share.id,
        "permission": share.permission,
        "status": share.status,
        "grantee_user_id": share.grantee_user_id,
        "grantee_team_id": share.grantee_team_id,
        "starts_at": share.starts_at,
        "expires_at": share.expires_at,
        "parent_share_id": share.parent_share_id,
    }


@router.delete("/shares/{share_id}")
async def revoke_share(
    share_id: int,
    data: RevokeIn | None = None,
    ctx: SecurityContext = Depends(require_permission("share.revoke")),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke a share and everything granted through it.

    Returns what was affected, so the UI can say "this also removed access for
    3 other people" rather than silently cutting them off.
    """
    share = (
        await db.execute(select(Share).where(Share.id == share_id))
    ).scalars().first()
    if not share:
        raise HTTPException(404, "Share not found.")

    affected = await shares.revoke(
        db, ctx=ctx, share=share, reason=(data.reason if data else None)
    )
    await db.commit()

    return {
        "revoked": len(affected),
        "cascaded": len(affected) - 1,
        "shares": [
            {
                "id": s.id,
                "grantee_user_id": s.grantee_user_id,
                "grantee_team_id": s.grantee_team_id,
                "was_cascade": s.id != share.id,
            }
            for s in affected
        ],
    }
