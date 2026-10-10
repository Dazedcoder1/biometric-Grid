"""
Oversight: an administrator looking into the vaults of the people they
administer — and, for the Super Admin, changing what is in them.

The ordinary vault routes answer "what can *I* reach" — what I own, plus what
was shared with me. These answer "what do the people I look after hold",
which is a different question with a different shape of risk, so it gets its
own routes rather than a flag on the old ones.

Who is in reach is oversight_service's rule: a Super Admin reaches everyone in
the organisation they are working in (X-Acting-Tenant-Id), Tenant Admins
included; a Tenant Admin their organisation; an Org Admin their department.

Safeguards, all required, none optional — including for the Super Admin:

  1. Scope, as above, one organisation at a time.
  2. A fresh second factor for every reveal and every change
     (credential.oversee requires step-up), exactly like revealing your own.
  3. Visibility. Each reveal or change is written to the audit log BEFORE it
     happens — filed under the organisation, so its own admins see it — and
     the owner is notified in the same transaction. If either cannot be
     written, nothing is revealed or changed.

Listing someone's credentials (names, usernames, no secrets) is audited too,
but does not notify — it is what an offboarding review looks like, and a
notification for every glance would teach people to ignore them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import (
    SecurityContext, require_organisation, require_permission, require_step_up,
)
from app.api.routes.vault.credentials import _out
from app.core import audit
from app.db.session import get_db
from app.services import dependency_service as deps
from app.services import notification_service
from app.services import oversight_service as oversight
from app.services import vault_service as svc

router = APIRouter()


class ChangeSecretIn(BaseModel):
    secret: str = Field(..., min_length=1)
    # Set once the caller has seen which production systems still hold the
    # old value. Same soft gate as the owner's own rotate route.
    acknowledge_impact: bool = False


async def _overseen_credential(db: AsyncSession, ctx: SecurityContext, credential_id: int):
    """
    The credential and its owner, if this admin may act on it. 404 for every
    failure — "no such credential" and "not yours" look the same, so the route
    cannot be used to map what exists in other departments or organisations.
    """
    org = require_organisation(ctx)
    cred = await svc.get_credential(db, credential_id)
    if cred.tenant_id != org:
        raise HTTPException(404, "Credential not found.")
    if cred.owner_id == ctx.user.id:
        raise HTTPException(400, "This is your own credential — use your vault for it.")
    try:
        owner = await oversight.get_overseeable(db, ctx.user, cred.owner_id, org)
    except HTTPException:
        raise HTTPException(404, "Credential not found.") from None
    return cred, owner


@router.get("/oversight/people")
async def oversight_people(
    ctx: SecurityContext = Depends(require_permission("credential.oversee")),
    db: AsyncSession = Depends(get_db),
):
    """You first (if you belong to this organisation), then everyone you look after."""
    org = require_organisation(ctx)
    return await oversight.people(db, ctx.user, org)


@router.get("/oversight/people/{user_id}/credentials")
async def oversight_credentials(
    user_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.oversee")),
    db: AsyncSession = Depends(get_db),
):
    """Everything this person owns. Metadata only — no secret leaves here."""
    org = require_organisation(ctx)

    if user_id == ctx.user.id:
        # Your own vault, through the same screen. Nothing to audit: looking
        # at your own things is not oversight.
        rows = await oversight.credentials_of(db, ctx.user.id)
        return {"person": {"id": ctx.user.id, "name": ctx.user.name, "is_me": True},
                "credentials": [_out(c) for c in rows]}

    person = await oversight.get_overseeable(db, ctx.user, user_id, org)
    rows = await oversight.credentials_of(db, person.id)

    await audit.record(
        db, action="vault.oversight_viewed", target_type="user", target_id=person.id,
        details={"name": person.name, "credentials": len(rows)},
        **ctx.audit_kwargs(),
    )
    await db.commit()

    return {"person": {"id": person.id, "name": person.name, "is_me": False},
            "credentials": [_out(c) for c in rows]}


@router.post("/oversight/credentials/{credential_id}/reveal")
async def oversight_reveal(
    credential_id: int,
    ctx: SecurityContext = Depends(require_step_up("credential.oversee")),
    db: AsyncSession = Depends(get_db),
):
    """
    Reveal a secret in the vault of someone you look after.

    Your own credentials do not come through here — use the ordinary reveal,
    which needs no oversight permission and notifies nobody.
    """
    cred, owner = await _overseen_credential(db, ctx, credential_id)

    # Written before decryption. If this row cannot be written, nothing is
    # revealed — see vault_service's module docstring.
    await audit.record(
        db, action="credential.revealed_by_admin", target_type="credential",
        target_id=cred.id, mfa_method="totp",
        details={"name": cred.name, "owner_id": owner.id, "owner_name": owner.name},
        **ctx.audit_kwargs(),
    )

    result = await svc.reveal(db, ctx=ctx, credential=cred)

    await notification_service.notify_single_user(
        db,
        tenant_id=owner.tenant_id,
        actor_id=ctx.user.id,
        recipient_id=owner.id,
        event_type="vault_admin_reveal",
        title="An administrator viewed one of your vault passwords",
        message=(
            f"{ctx.user.name} revealed “{cred.name}” from your vault. "
            "If you did not expect this, change that password."
        ),
        entity_type="credential",
        entity_id=cred.id,
        entity_name=cred.name,
    )

    # One commit for the audit rows, the notification and last_accessed_at.
    # Nothing has been sent yet; if this fails, neither has the secret.
    await db.commit()
    return result


@router.post("/oversight/credentials/{credential_id}/change")
async def oversight_change_secret(
    credential_id: int,
    data: ChangeSecretIn,
    ctx: SecurityContext = Depends(require_step_up("credential.oversee")),
    db: AsyncSession = Depends(get_db),
):
    """
    Put a new secret into someone else's credential. Super Admin only.

    A new version, like any rotation — the previous one is kept. Refused until
    acknowledged when production systems depend on it, with the list of what
    will break, exactly as the owner's own rotate route does: an administrator
    changing a password is no less able to cause an outage than its owner.
    """
    if not ctx.permissions.grants_all:
        # Tenant and Org Admins may look, not change. Changing another
        # person's secrets is the platform operator's call alone.
        raise HTTPException(403, "Only a Super Admin can change someone else's saved password.")

    cred, owner = await _overseen_credential(db, ctx, credential_id)

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

    await audit.record(
        db, action="credential.changed_by_admin", target_type="credential",
        target_id=cred.id, mfa_method="totp",
        details={"name": cred.name, "owner_id": owner.id, "owner_name": owner.name,
                 "systems_to_update": [s["name"] for s in impact["systems"]]},
        **ctx.audit_kwargs(),
    )
    version = await svc.rotate(db, ctx=ctx, credential=cred, secret=data.secret)

    await notification_service.notify_single_user(
        db,
        tenant_id=owner.tenant_id,
        actor_id=ctx.user.id,
        recipient_id=owner.id,
        event_type="vault_admin_change",
        title="An administrator changed one of your vault passwords",
        message=(
            f"{ctx.user.name} set a new password on “{cred.name}”. Reveal it from "
            "your vault to see the new value. The previous one is kept as an "
            "earlier version."
        ),
        entity_type="credential",
        entity_id=cred.id,
        entity_name=cred.name,
    )

    await db.commit()
    return {
        "version": version.version,
        "update_these_systems": [s["name"] for s in impact["systems"]],
    }
