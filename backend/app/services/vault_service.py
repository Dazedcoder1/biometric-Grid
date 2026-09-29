"""
Vault, rack and credential operations.

Access resolution lives here rather than in the routes, so there is exactly one
implementation of "may this person touch this credential" and every caller gets
the same answer. A second copy in a route handler is how authorisation bugs are
born.

Ordering rule that matters: the audit entry for a reveal is written BEFORE the
decryption, and the caller commits. If the audit write fails the reveal fails.
An unlogged reveal must be impossible, including when the process dies
mid-request.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit, envelope
from app.models.credentials import (
    Credential,
    CredentialVersion,
    EncryptedPayload,
    OwnershipHistory,
    Rack,
    Share,
    TeamMember,
    Vault,
)
from app.models.domain import User

# Permission levels, ordered weakest to strongest. A share at one level implies
# everything below it — `manage` can obviously view.
LEVELS = ("view", "reveal", "edit", "reshare", "manage")
_RANK = {name: i for i, name in enumerate(LEVELS)}

DEFAULT_RACKS = (
    ("General", "folder"),
    ("GitHub", "github"),
    ("Google", "globe"),
    ("Databases", "database"),
)


# ─────────────────────────────────────────────────────────────────────────────
# Provisioning
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_vaults(db: AsyncSession, user: User) -> dict[str, Vault]:
    """
    Guarantee this user has a personal and a shared vault. Idempotent.

    Called on first access rather than at signup, so the several hundred users
    who already exist get vaults without a backfill migration.

    The SHARED vault stores nothing — its contents are computed from active
    shares. It exists as a stable container for the UI to render.
    """
    rows = (
        await db.execute(select(Vault).where(Vault.owner_user_id == user.id))
    ).scalars().all()
    by_kind = {v.kind: v for v in rows}

    created = False
    if "personal" not in by_kind:
        personal = Vault(
            tenant_id=user.tenant_id,
            owner_user_id=user.id,
            kind="personal",
            name="Personal Vault",
        )
        db.add(personal)
        await db.flush()
        for order, (name, icon) in enumerate(DEFAULT_RACKS):
            db.add(Rack(vault_id=personal.id, name=name, icon=icon, sort_order=order))
        by_kind["personal"] = personal
        created = True

    if "shared" not in by_kind:
        shared = Vault(
            tenant_id=user.tenant_id,
            owner_user_id=user.id,
            kind="shared",
            name="Shared with me",
        )
        db.add(shared)
        await db.flush()
        by_kind["shared"] = shared
        created = True

    if created:
        await db.flush()
    return by_kind


# ─────────────────────────────────────────────────────────────────────────────
# Access resolution
# ─────────────────────────────────────────────────────────────────────────────


async def effective_level(
    db: AsyncSession, *, user: User, credential: Credential, grants_all: bool = False
) -> str | None:
    """
    The strongest permission this user holds on this credential, or None.

    Sources, in order:
      1. Super Admin — everything, by requirement. Audited separately because
         it bypasses sharing entirely.
      2. Ownership — the owner has `manage`.
      3. A direct share to the user.
      4. A share to a team they belong to.

    Tenant isolation is checked FIRST and independently of grants. A share row
    pointing across tenants — however it got there — cannot grant access.
    """
    if credential.tenant_id != user.tenant_id and not grants_all:
        return None

    if grants_all:
        return "manage"

    if credential.owner_id == user.id:
        return "manage"

    now = datetime.now(timezone.utc)

    team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)

    rows = (
        await db.execute(
            select(Share.permission).where(
                Share.credential_id == credential.id,
                Share.status == "active",
                or_(
                    Share.grantee_user_id == user.id,
                    Share.grantee_team_id.in_(team_ids),
                ),
                or_(Share.starts_at.is_(None), Share.starts_at <= now),
                or_(Share.expires_at.is_(None), Share.expires_at > now),
            )
        )
    ).scalars().all()

    if not rows:
        return None
    return max(rows, key=lambda p: _RANK.get(p, -1))


def allows(level: str | None, required: str) -> bool:
    """Deny-by-default: an unknown or absent level satisfies nothing."""
    if level is None:
        return False
    return _RANK.get(level, -1) >= _RANK.get(required, 99)


async def require_level(
    db: AsyncSession, *, user: User, credential: Credential, required: str,
    grants_all: bool = False,
) -> str:
    level = await effective_level(
        db, user=user, credential=credential, grants_all=grants_all
    )
    if not allows(level, required):
        # 404 rather than 403 when there is no access at all. Distinguishing
        # "exists but forbidden" from "does not exist" lets someone enumerate
        # credential ids to learn what a tenant holds.
        raise HTTPException(404, "Credential not found.")
    return level


# ─────────────────────────────────────────────────────────────────────────────
# Queries
# ─────────────────────────────────────────────────────────────────────────────


async def list_credentials(
    db: AsyncSession,
    *,
    user: User,
    grants_all: bool = False,
    rack_id: int | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Credential]:
    """
    Everything this user can see: owned, plus actively shared.

    Never returns ciphertext — that table is not even joined. Reveal is the
    only path that touches it.
    """
    now = datetime.now(timezone.utc)
    q = select(Credential).where(Credential.deleted_at.is_(None))

    if grants_all:
        pass  # super admin sees every tenant
    else:
        team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
        shared = select(Share.credential_id).where(
            Share.status == "active",
            or_(
                Share.grantee_user_id == user.id,
                Share.grantee_team_id.in_(team_ids),
            ),
            or_(Share.starts_at.is_(None), Share.starts_at <= now),
            or_(Share.expires_at.is_(None), Share.expires_at > now),
        )
        q = q.where(
            Credential.tenant_id == user.tenant_id,
            or_(Credential.owner_id == user.id, Credential.id.in_(shared)),
        )

    if rack_id:
        q = q.where(Credential.rack_id == rack_id)
    if search:
        pattern = f"%{search.strip()}%"
        q = q.where(
            or_(
                Credential.name.ilike(pattern),
                Credential.username.ilike(pattern),
                Credential.url.ilike(pattern),
            )
        )

    q = q.order_by(Credential.name).limit(min(limit, 500)).offset(offset)
    return list((await db.execute(q)).scalars().all())


async def get_credential(db: AsyncSession, credential_id: int) -> Credential:
    cred = (
        await db.execute(
            select(Credential).where(
                Credential.id == credential_id, Credential.deleted_at.is_(None)
            )
        )
    ).scalars().first()
    if not cred:
        raise HTTPException(404, "Credential not found.")
    return cred


# ─────────────────────────────────────────────────────────────────────────────
# Mutations
# ─────────────────────────────────────────────────────────────────────────────


async def create_credential(
    db: AsyncSession, *, ctx, rack_id: int, name: str, secret: str,
    kind: str = "password", username: str | None = None, url: str | None = None,
    notes: str | None = None, has_2fa: bool = False,
) -> Credential:
    """
    Create a credential and its first version.

    `notes` is encrypted alongside the secret, not stored as metadata — notes
    are where people write recovery codes.
    """
    rack = (
        await db.execute(
            select(Rack).join(Vault, Vault.id == Rack.vault_id).where(
                Rack.id == rack_id,
                Vault.tenant_id == ctx.user.tenant_id,
            )
        )
    ).scalars().first()
    if not rack:
        raise HTTPException(404, "Rack not found.")

    cred = Credential(
        tenant_id=ctx.user.tenant_id,
        rack_id=rack_id,
        owner_id=ctx.user.id,
        created_by=ctx.user.id,
        name=name.strip(),
        kind=kind,
        username=username,
        url=url,
        has_2fa=has_2fa,
    )
    db.add(cred)
    await db.flush()

    await _write_version(db, credential=cred, secret=secret, notes=notes, actor_id=ctx.user.id)

    db.add(
        OwnershipHistory(
            credential_id=cred.id,
            from_user_id=None,
            to_user_id=ctx.user.id,
            changed_by=ctx.user.id,
            reason="created",
        )
    )

    await audit.record(
        db,
        action="credential.created",
        target_type="credential",
        target_id=cred.id,
        details={"name": cred.name, "kind": kind, "rack_id": rack_id},
        **ctx.audit_kwargs(),
    )
    return cred


async def _write_version(
    db: AsyncSession, *, credential: Credential, secret: str,
    notes: str | None, actor_id: int,
) -> CredentialVersion:
    """Encrypt and append a version. Updates the current-version pointer."""
    next_version = (
        await db.execute(
            select(func.coalesce(func.max(CredentialVersion.version), 0)).where(
                CredentialVersion.credential_id == credential.id
            )
        )
    ).scalar_one() + 1

    # Secret and notes travel together under one key. Separating them would
    # mean two DEKs and two unwraps for something always revealed together.
    payload_text = secret if notes is None else f"{secret}\x00{notes}"

    aad = envelope.build_aad(credential.tenant_id, credential.id, next_version)
    blob = envelope.encrypt(payload_text, aad=aad)

    payload = EncryptedPayload(
        ciphertext=blob.ciphertext,
        nonce=blob.nonce,
        wrapped_dek=blob.wrapped_dek,
        kek_id=blob.kek_id,
        alg=blob.alg,
        aad_context=aad.decode(),
    )
    db.add(payload)
    await db.flush()

    version = CredentialVersion(
        credential_id=credential.id,
        version=next_version,
        payload_id=payload.id,
        created_by=actor_id,
    )
    db.add(version)
    await db.flush()

    credential.current_version_id = version.id
    credential.updated_at = datetime.now(timezone.utc)
    return version


async def reveal(db: AsyncSession, *, ctx, credential: Credential) -> dict:
    """
    Decrypt and return the secret.

    The audit entry is written first, deliberately. If it cannot be written the
    reveal does not happen — see the module docstring.
    """
    await audit.record(
        db,
        action="credential.revealed",
        target_type="credential",
        target_id=credential.id,
        mfa_method="totp",
        details={"name": credential.name, "owner_id": credential.owner_id},
        **ctx.audit_kwargs(),
    )

    version = (
        await db.execute(
            select(CredentialVersion).where(
                CredentialVersion.id == credential.current_version_id
            )
        )
    ).scalars().first()
    if not version or not version.payload_id:
        raise HTTPException(409, "This credential has no stored secret.")

    payload = (
        await db.execute(
            select(EncryptedPayload).where(EncryptedPayload.id == version.payload_id)
        )
    ).scalars().first()
    if not payload:
        raise HTTPException(409, "The stored payload is missing.")

    blob = envelope.Envelope(
        ciphertext=payload.ciphertext,
        nonce=payload.nonce,
        wrapped_dek=payload.wrapped_dek,
        kek_id=payload.kek_id,
        alg=payload.alg,
    )
    aad = envelope.build_aad(credential.tenant_id, credential.id, version.version)

    try:
        plaintext = envelope.decrypt(blob, aad=aad)
    except envelope.TamperDetected as exc:
        # A failed tag is a security event, not a glitch. Recorded distinctly
        # so it can be alerted on.
        await audit.record(
            db,
            action="credential.tamper_detected",
            result="error",
            reason=str(exc),
            target_type="credential",
            target_id=credential.id,
            **ctx.audit_kwargs(),
        )
        raise HTTPException(500, "Stored payload failed integrity checks.") from exc

    secret, _, notes = plaintext.partition("\x00")
    credential.last_accessed_at = datetime.now(timezone.utc)

    return {"secret": secret, "notes": notes or None, "version": version.version}


async def rotate(db: AsyncSession, *, ctx, credential: Credential,
                 secret: str, notes: str | None = None) -> CredentialVersion:
    """Append a new version. The old one is retained per decision 8."""
    version = await _write_version(
        db, credential=credential, secret=secret, notes=notes, actor_id=ctx.user.id
    )
    await audit.record(
        db,
        action="credential.rotated",
        target_type="credential",
        target_id=credential.id,
        details={"version": version.version},
        **ctx.audit_kwargs(),
    )
    return version


async def soft_delete(db: AsyncSession, *, ctx, credential: Credential) -> None:
    credential.deleted_at = datetime.now(timezone.utc)
    await audit.record(
        db,
        action="credential.deleted",
        target_type="credential",
        target_id=credential.id,
        details={"name": credential.name},
        **ctx.audit_kwargs(),
    )
