"""
Credential dependency map: what uses a credential, and what breaks if it changes.

The point of this module is `impact_of`. Rotating a database password is
trivial until you discover it was also in a CI pipeline, a cron job and a
container's environment — and you discover that because three things broke at
04:00. Recording dependencies turns that from an outage into a checklist.

Systems are first-class rows rather than free text on the credential. One
Postgres instance is depended on by several credentials, and the org-wide view
only means something if "production-postgres" is the same node everywhere
rather than four spellings of it.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.models.credentials import Credential, CredentialDependency, Share, System

#: Suggested when creating a system. Free text is still allowed — an
#: organisation will always have something this list has not heard of.
COMMON_KINDS = (
    "database", "ci", "container", "api", "saas", "infrastructure",
    "monitoring", "messaging", "storage", "other",
)


# ─────────────────────────────────────────────────────────────────────────────
# Systems
# ─────────────────────────────────────────────────────────────────────────────


async def list_systems(db: AsyncSession, *, tenant_id: int) -> list[dict]:
    """Systems with how many credentials each depends on."""
    rows = (
        await db.execute(
            select(System, func.count(CredentialDependency.id))
            .outerjoin(CredentialDependency, CredentialDependency.system_id == System.id)
            .where(System.tenant_id == tenant_id)
            .group_by(System.id)
            .order_by(System.name)
        )
    ).all()

    return [
        {
            "id": s.id,
            "name": s.name,
            "kind": s.kind,
            "environment": s.environment,
            "description": s.description,
            "credential_count": count,
        }
        for s, count in rows
    ]


async def upsert_system(
    db: AsyncSession, *, ctx, name: str, kind: str | None,
    environment: str | None, description: str | None = None,
) -> System:
    """
    Find or create. Idempotent on (tenant, name, environment).

    Upsert rather than create because the natural flow is "link this credential
    to production-postgres" — and the user should not have to know whether that
    system already exists. A strict create would produce duplicates the moment
    two people link the same system on the same afternoon.
    """
    name = name.strip()
    existing = (
        await db.execute(
            select(System).where(
                System.tenant_id == ctx.user.tenant_id,
                System.name == name,
                System.environment == environment,
            )
        )
    ).scalars().first()
    if existing:
        return existing

    system = System(
        tenant_id=ctx.user.tenant_id,
        name=name,
        kind=kind,
        environment=environment,
        description=description,
    )
    db.add(system)
    await db.flush()

    await audit.record(
        db, action="system.created", target_type="system", target_id=system.id,
        details={"name": name, "environment": environment}, **ctx.audit_kwargs(),
    )
    return system


# ─────────────────────────────────────────────────────────────────────────────
# Links
# ─────────────────────────────────────────────────────────────────────────────


async def link(
    db: AsyncSession, *, ctx, credential: Credential, system: System,
    notes: str | None = None,
) -> CredentialDependency:
    existing = (
        await db.execute(
            select(CredentialDependency).where(
                CredentialDependency.credential_id == credential.id,
                CredentialDependency.system_id == system.id,
            )
        )
    ).scalars().first()
    if existing:
        if notes:
            existing.notes = notes
        return existing

    dep = CredentialDependency(
        credential_id=credential.id,
        system_id=system.id,
        notes=notes,
        created_by=ctx.user.id,
    )
    db.add(dep)
    await db.flush()

    await audit.record(
        db, action="dependency.linked", target_type="credential",
        target_id=credential.id,
        details={"system_id": system.id, "system": system.name},
        **ctx.audit_kwargs(),
    )
    return dep


async def unlink(db: AsyncSession, *, ctx, dependency_id: int) -> None:
    dep = (
        await db.execute(
            select(CredentialDependency).where(CredentialDependency.id == dependency_id)
        )
    ).scalars().first()
    if not dep:
        raise HTTPException(404, "Dependency not found.")

    await db.delete(dep)
    await audit.record(
        db, action="dependency.unlinked", target_type="credential",
        target_id=dep.credential_id, details={"system_id": dep.system_id},
        **ctx.audit_kwargs(),
    )


async def for_credential(db: AsyncSession, credential_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(CredentialDependency, System)
            .join(System, System.id == CredentialDependency.system_id)
            .where(CredentialDependency.credential_id == credential_id)
            .order_by(System.name)
        )
    ).all()

    return [
        {
            "dependency_id": d.id,
            "system_id": s.id,
            "name": s.name,
            "kind": s.kind,
            "environment": s.environment,
            "notes": d.notes,
        }
        for d, s in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Blast radius
# ─────────────────────────────────────────────────────────────────────────────


async def impact_of(
    db: AsyncSession, *, credential: Credential, action: str = "rotate"
) -> dict:
    """
    What breaks if this credential is rotated or revoked.

    Two distinct consequences, deliberately reported separately:

      - **Systems** stop working on rotation. They hold the old secret in a
        config file or environment variable and will keep presenting it until
        somebody updates them.
      - **People** lose access on revocation. Rotation does not affect them;
        they read the new value from here.

    Conflating the two produces a warning that is wrong for whichever action
    you are actually taking.
    """
    systems = (
        await db.execute(
            select(System, CredentialDependency.notes)
            .join(CredentialDependency, CredentialDependency.system_id == System.id)
            .where(CredentialDependency.credential_id == credential.id)
            .order_by(System.environment.desc().nullslast(), System.name)
        )
    ).all()

    share_count = (
        await db.execute(
            select(func.count(Share.id)).where(
                Share.credential_id == credential.id, Share.status == "active"
            )
        )
    ).scalar_one()

    affected = []
    for system, notes in systems:
        # Other credentials the same system needs. Useful context: if you are
        # already taking a maintenance window for this system, you may want to
        # rotate its other secrets at the same time.
        siblings = (
            await db.execute(
                select(func.count(CredentialDependency.id)).where(
                    CredentialDependency.system_id == system.id,
                    CredentialDependency.credential_id != credential.id,
                )
            )
        ).scalar_one()

        affected.append({
            "system_id": system.id,
            "name": system.name,
            "kind": system.kind,
            "environment": system.environment,
            "notes": notes,
            "other_credentials": siblings,
            # Production first, and called out — the difference between an
            # inconvenience and an incident.
            "is_production": (system.environment or "").lower() in ("production", "prod"),
        })

    production = [a for a in affected if a["is_production"]]

    if action == "revoke":
        summary = (
            f"{share_count} " + ("person loses" if share_count == 1 else "people lose")
            + " access."
        ) if share_count else "Nobody currently has access through a share."
    else:
        if not affected:
            summary = (
                "Nothing is recorded as depending on this. That may mean it is "
                "genuinely unused — or that the dependency map is incomplete."
            )
        else:
            summary = (
                f"{len(affected)} system"
                + ("" if len(affected) == 1 else "s")
                + " will keep presenting the old secret until updated"
                + (f", {len(production)} in production." if production else ".")
            )

    return {
        "credential_id": credential.id,
        "credential_name": credential.name,
        "action": action,
        "summary": summary,
        "systems": affected,
        "production_systems": len(production),
        "people_with_access": share_count,
        # The UI uses this to decide between a confirm dialog and a
        # type-the-name-to-continue prompt.
        "requires_care": bool(production) or share_count > 5,
    }


async def org_graph(db: AsyncSession, *, tenant_id: int) -> dict:
    """
    The whole map as nodes and edges.

    Bipartite by nature — credentials on one side, systems on the other, edges
    only between them. That shape is what makes it renderable as two columns
    rather than needing a force-directed layout.
    """
    creds = (
        await db.execute(
            select(Credential.id, Credential.name, Credential.kind)
            .where(Credential.tenant_id == tenant_id, Credential.deleted_at.is_(None))
            .order_by(Credential.name)
        )
    ).all()

    systems = (
        await db.execute(
            select(System.id, System.name, System.kind, System.environment)
            .where(System.tenant_id == tenant_id)
            .order_by(System.name)
        )
    ).all()

    edges = (
        await db.execute(
            select(CredentialDependency.credential_id, CredentialDependency.system_id)
            .join(Credential, Credential.id == CredentialDependency.credential_id)
            .where(Credential.tenant_id == tenant_id, Credential.deleted_at.is_(None))
        )
    ).all()

    linked_creds = {c for c, _ in edges}
    linked_systems = {s for _, s in edges}

    return {
        "credentials": [
            {
                "id": cid, "name": name, "kind": kind,
                # Surfaced rather than hidden: an unmapped credential is not a
                # safe one, it is one whose blast radius is unknown.
                "unmapped": cid not in linked_creds,
            }
            for cid, name, kind in creds
        ],
        "systems": [
            {
                "id": sid, "name": name, "kind": kind, "environment": env,
                "orphaned": sid not in linked_systems,
            }
            for sid, name, kind, env in systems
        ],
        "edges": [{"credential_id": c, "system_id": s} for c, s in edges],
        "stats": {
            "credentials": len(creds),
            "systems": len(systems),
            "links": len(edges),
            "unmapped_credentials": len(creds) - len(linked_creds),
        },
    }
