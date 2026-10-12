"""
Remove organisations and everything that hangs off them.

One implementation, used by the demo seed's --reset and by the Super Admin's
"delete organisation and everything in it". It began life inside
seed_demo_data.py; it lives here now so the Organisations screen deletes in
exactly the order that has already been run against a real database, rather
than a second copy that could drift from it.

Ordered child-first. Several foreign keys are RESTRICT rather than CASCADE —
deliberately, so that a user or rack holding credentials cannot be deleted
out from under them — which means the order is load-bearing, not stylistic.

The audit log is not touched. It has no foreign key to organisations, and the
record that an organisation existed, and who deleted it, outlives it.

Does not commit. The caller commits, so the deletion and its audit entry land
together or not at all.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credentials import (
    Credential,
    CredentialDependency,
    CredentialVersion,
    EncryptedPayload,
    OwnershipHistory,
    Rack,
    RotationPolicy,
    Share,
    System,
    Team,
    TeamMember,
    Vault,
)
from app.models.domain import (
    AttendanceLog,
    Command,
    Department,
    Device,
    GitHubRepo,
    Holiday,
    Leave,
    Notification,
    Settings,
    Task,
    Tenant,
    User,
)


async def purge_tenants(db: AsyncSession, ids: list[int]) -> int:
    """Delete these organisations and all their data. Returns how many."""
    ids = [i for i in ids if i is not None]
    if not ids:
        return 0

    vault_ids = [v.id for v in (await db.execute(
        select(Vault).where(Vault.tenant_id.in_(ids)))).scalars().all()]
    cred_ids = [c.id for c in (await db.execute(
        select(Credential).where(Credential.tenant_id.in_(ids)))).scalars().all()]
    team_ids = [t.id for t in (await db.execute(
        select(Team).where(Team.tenant_id.in_(ids)))).scalars().all()]

    if cred_ids:
        versions = (await db.execute(
            select(CredentialVersion.id, CredentialVersion.payload_id)
            .where(CredentialVersion.credential_id.in_(cred_ids)))).all()
        version_ids = [v for v, _p in versions]
        payload_ids = [p for _v, p in versions if p]

        await db.execute(delete(CredentialDependency)
                         .where(CredentialDependency.credential_id.in_(cred_ids)))
        await db.execute(delete(RotationPolicy).where(RotationPolicy.tenant_id.in_(ids)))
        await db.execute(delete(Share).where(Share.tenant_id.in_(ids)))
        await db.execute(delete(OwnershipHistory)
                         .where(OwnershipHistory.credential_id.in_(cred_ids)))
        # Credentials point at their current version, and versions point back
        # at the credential. Break the forward pointer first or the delete is
        # refused.
        await db.execute(
            Credential.__table__.update()
            .where(Credential.id.in_(cred_ids)).values(current_version_id=None)
        )
        if version_ids:
            await db.execute(delete(CredentialVersion)
                             .where(CredentialVersion.id.in_(version_ids)))
        if payload_ids:
            await db.execute(delete(EncryptedPayload)
                             .where(EncryptedPayload.id.in_(payload_ids)))
        await db.execute(delete(Credential).where(Credential.id.in_(cred_ids)))
    else:
        await db.execute(delete(RotationPolicy).where(RotationPolicy.tenant_id.in_(ids)))
        await db.execute(delete(Share).where(Share.tenant_id.in_(ids)))

    if team_ids:
        await db.execute(delete(TeamMember).where(TeamMember.team_id.in_(team_ids)))
    await db.execute(delete(Team).where(Team.tenant_id.in_(ids)))
    await db.execute(delete(System).where(System.tenant_id.in_(ids)))
    if vault_ids:
        await db.execute(delete(Rack).where(Rack.vault_id.in_(vault_ids)))
    await db.execute(delete(Vault).where(Vault.tenant_id.in_(ids)))

    await db.execute(delete(Notification).where(Notification.tenant_id.in_(ids)))
    await db.execute(delete(AttendanceLog).where(AttendanceLog.tenant_id.in_(ids)))
    await db.execute(delete(Leave).where(Leave.tenant_id.in_(ids)))
    await db.execute(delete(Holiday).where(Holiday.tenant_id.in_(ids)))
    await db.execute(delete(Command).where(Command.tenant_id.in_(ids)))
    await db.execute(delete(Device).where(Device.tenant_id.in_(ids)))
    # Tasks before the repositories they mirror; comments go with their task.
    await db.execute(delete(Task).where(Task.tenant_id.in_(ids)))
    await db.execute(delete(GitHubRepo).where(GitHubRepo.tenant_id.in_(ids)))
    await db.execute(delete(Settings).where(Settings.tenant_id.in_(ids)))
    await db.execute(delete(User).where(User.tenant_id.in_(ids)))
    await db.execute(delete(Department).where(Department.tenant_id.in_(ids)))
    await db.execute(delete(Tenant).where(Tenant.id.in_(ids)))
    return len(ids)
