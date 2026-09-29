"""
Vaults, racks and credentials.

Two guards are in play. `require_permission` checks what the user's ROLE
allows in general; `vault_service.require_level` checks what their SHARE
allows on this specific credential. Both must pass — a role that permits
revealing does not grant access to every credential.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import (
    SecurityContext,
    get_security_context,
    require_permission,
    require_step_up,
)
from app.core import audit
from app.db.session import get_db
from app.models.credentials import Rack, Vault
from app.services import dependency_service as deps
from app.services import vault_service as svc

router = APIRouter()


# ─── schemas ─────────────────────────────────────────────────────────────────

class RackIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    icon: str | None = Field(None, max_length=64)


class CredentialIn(BaseModel):
    rack_id: int
    name: str = Field(..., min_length=1, max_length=255)
    secret: str = Field(..., min_length=1)
    kind: str = "password"
    username: str | None = Field(None, max_length=255)
    url: str | None = None
    notes: str | None = None
    has_2fa: bool = False


class CredentialPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    username: str | None = None
    url: str | None = None
    has_2fa: bool | None = None


class RotateIn(BaseModel):
    secret: str = Field(..., min_length=1)
    notes: str | None = None
    # Set once the caller has seen the impact preview. Required when a
    # production system depends on this credential — see the rotate route.
    acknowledge_impact: bool = False


def _out(c) -> dict:
    """
    Metadata only. There is no code path from this function to the ciphertext,
    which is what keeps a secret out of a list response by construction rather
    than by remembering.
    """
    return {
        "id": c.id,
        "name": c.name,
        "kind": c.kind,
        "username": c.username,
        "url": c.url,
        "has_2fa": c.has_2fa,
        "rack_id": c.rack_id,
        "owner_id": c.owner_id,
        "expires_at": c.expires_at,
        "last_accessed_at": c.last_accessed_at,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


# ─── vaults and racks ────────────────────────────────────────────────────────

@router.get("/vaults")
async def my_vaults(
    ctx: SecurityContext = Depends(require_permission("vault.view")),
    db: AsyncSession = Depends(get_db),
):
    """Personal and shared vaults, created on first call."""
    vaults = await svc.ensure_vaults(db, ctx.user)
    await db.commit()

    out = []
    for kind in ("personal", "shared"):
        v = vaults[kind]
        racks = (
            await db.execute(
                select(Rack).where(Rack.vault_id == v.id).order_by(Rack.sort_order)
            )
        ).scalars().all()
        out.append({
            "id": v.id,
            "kind": v.kind,
            "name": v.name,
            "racks": [
                {"id": r.id, "name": r.name, "icon": r.icon, "sort_order": r.sort_order}
                for r in racks
            ],
        })
    return out


@router.post("/racks", status_code=201)
async def create_rack(
    data: RackIn,
    vault_id: int = Query(...),
    ctx: SecurityContext = Depends(require_permission("rack.manage")),
    db: AsyncSession = Depends(get_db),
):
    vault = (
        await db.execute(
            select(Vault).where(
                Vault.id == vault_id, Vault.owner_user_id == ctx.user.id
            )
        )
    ).scalars().first()
    if not vault:
        raise HTTPException(404, "Vault not found.")
    if vault.kind == "shared":
        raise HTTPException(
            400,
            "The shared vault holds no racks — its contents come from shares.",
        )

    rack = Rack(vault_id=vault.id, name=data.name.strip(), icon=data.icon)
    db.add(rack)
    await db.flush()

    await audit.record(
        db, action="rack.created", target_type="rack", target_id=rack.id,
        details={"name": rack.name}, **ctx.audit_kwargs(),
    )
    await db.commit()
    return {"id": rack.id, "name": rack.name, "icon": rack.icon}


# ─── credentials ─────────────────────────────────────────────────────────────

@router.get("/credentials")
async def list_credentials(
    rack_id: int | None = None,
    search: str | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    rows = await svc.list_credentials(
        db, user=ctx.user, grants_all=ctx.permissions.grants_all,
        rack_id=rack_id, search=search, limit=limit, offset=offset,
    )
    return [_out(c) for c in rows]


@router.post("/credentials", status_code=201)
async def create_credential(
    data: CredentialIn,
    ctx: SecurityContext = Depends(require_permission("credential.create")),
    db: AsyncSession = Depends(get_db),
):
    cred = await svc.create_credential(
        db, ctx=ctx, rack_id=data.rack_id, name=data.name, secret=data.secret,
        kind=data.kind, username=data.username, url=data.url,
        notes=data.notes, has_2fa=data.has_2fa,
    )
    await db.commit()
    return _out(cred)


@router.get("/credentials/{credential_id}")
async def get_credential(
    credential_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    cred = await svc.get_credential(db, credential_id)
    level = await svc.require_level(
        db, user=ctx.user, credential=cred, required="view",
        grants_all=ctx.permissions.grants_all,
    )
    return {**_out(cred), "my_permission": level}


@router.post("/credentials/{credential_id}/reveal")
async def reveal_credential(
    credential_id: int,
    ctx: SecurityContext = Depends(require_step_up("credential.reveal")),
    db: AsyncSession = Depends(get_db),
):
    """
    Decrypt and return the secret. Requires the role permission, a share at
    `reveal` or above, AND a fresh MFA assertion in `X-Step-Up-Token`.

    Callers without the header get 401 with `X-Step-Up-Required`, which the
    frontend uses to prompt for a code and retry.
    """
    cred = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=cred, required="reveal",
        grants_all=ctx.permissions.grants_all,
    )

    result = await svc.reveal(db, ctx=ctx, credential=cred)
    await db.commit()
    return result


@router.post("/credentials/{credential_id}/copied", status_code=204)
async def record_copy(
    credential_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    Record that a revealed secret was copied to the clipboard.

    Deliberately NOT a permission. Copying cannot be prevented — anyone who can
    see a secret can retype it, screenshot it, or read it aloud. Offering a
    `copy` permission would advertise a control that does not exist. This makes
    the act observable, which is the honest half of the promise.
    """
    cred = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=cred, required="reveal",
        grants_all=ctx.permissions.grants_all,
    )
    await audit.record(
        db, action="credential.copied", target_type="credential",
        target_id=cred.id, **ctx.audit_kwargs(),
    )
    await db.commit()


@router.patch("/credentials/{credential_id}")
async def update_credential(
    credential_id: int,
    data: CredentialPatch,
    ctx: SecurityContext = Depends(require_permission("credential.edit")),
    db: AsyncSession = Depends(get_db),
):
    cred = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=cred, required="edit",
        grants_all=ctx.permissions.grants_all,
    )

    changed = []
    for field in ("name", "username", "url", "has_2fa"):
        value = getattr(data, field)
        if value is not None and value != getattr(cred, field):
            setattr(cred, field, value)
            changed.append(field)

    if changed:
        await audit.record(
            db, action="credential.updated", target_type="credential",
            target_id=cred.id, details={"fields": changed}, **ctx.audit_kwargs(),
        )
    await db.commit()
    return _out(cred)


@router.post("/credentials/{credential_id}/rotate")
async def rotate_credential(
    credential_id: int,
    data: RotateIn,
    ctx: SecurityContext = Depends(require_permission("credential.edit")),
    db: AsyncSession = Depends(get_db),
):
    """
    Store a new secret as a new version. The previous one is retained.

    If a production system depends on this credential, the call is refused
    until `acknowledge_impact` is set — and the refusal carries the impact
    report, so the caller learns *what* they are about to break rather than
    just being told to try again.

    A soft gate on purpose: it stops an absent-minded rotation, not a
    determined one. Rotation is often exactly the right response to a
    suspected compromise, and a control that made it hard would get worked
    around at the worst possible moment.
    """
    cred = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=cred, required="edit",
        grants_all=ctx.permissions.grants_all,
    )

    impact = await deps.impact_of(db, credential=cred, action="rotate")
    if impact["production_systems"] and not data.acknowledge_impact:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "impact_acknowledgement_required",
                "message": impact["summary"],
                "impact": impact,
                "retry_with": {"acknowledge_impact": True},
            },
        )

    version = await svc.rotate(db, ctx=ctx, credential=cred,
                              secret=data.secret, notes=data.notes)

    # Recorded on the rotation itself, so the audit trail shows what was known
    # to be at risk at the moment it happened — not what the dependency map
    # says today.
    if impact["systems"]:
        await audit.record(
            db,
            action="credential.rotation_impact",
            target_type="credential",
            target_id=cred.id,
            details={
                "systems": [s["name"] for s in impact["systems"]],
                "production_systems": impact["production_systems"],
            },
            **ctx.audit_kwargs(),
        )

    await db.commit()
    return {
        "version": version.version,
        "rotated_at": version.created_at,
        "update_these_systems": [s["name"] for s in impact["systems"]],
    }


@router.delete("/credentials/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.delete")),
    db: AsyncSession = Depends(get_db),
):
    cred = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=cred, required="manage",
        grants_all=ctx.permissions.grants_all,
    )
    await svc.soft_delete(db, ctx=ctx, credential=cred)
    await db.commit()
