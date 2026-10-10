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

Who sees what
-------------
Systems belong to a department, or to nobody (shared). One rule, `Scope`,
decides visibility for every query here:

    Tenant Admin   every system in the organisation
    everyone else  their own department's systems, plus shared ones

The map shows credentials only where they connect to a system you can see, or
where you can reach the credential anyway (your own, or shared with you). It
used to list every credential name in the company to every employee.

One deliberate exception: `impact_of` — "what breaks if I rotate this" — lists
every system the credential feeds, in any department. Hiding a production
system from the person about to rotate its password is how outages happen.
Systems outside your departments are labelled as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.models.credentials import (
    Credential, CredentialDependency, Share, System, TeamMember,
)
from app.models.domain import Department, User

#: Suggested when creating a system. Free text is still allowed — an
#: organisation will always have something this list has not heard of.
COMMON_KINDS = (
    "database", "ci", "container", "api", "saas", "infrastructure",
    "monitoring", "messaging", "storage", "other",
)


# ─────────────────────────────────────────────────────────────────────────────
# Scope
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scope:
    """Which systems one person can see. Build it with `scope_for`."""

    tenant_id: int | None
    all_departments: bool
    department_id: int | None

    def sees(self, system: System) -> bool:
        """Pure version of `clause`, for objects already loaded."""
        if system.tenant_id != self.tenant_id:
            return False
        if self.all_departments:
            return True
        return system.department_id is None or (
            self.department_id is not None and system.department_id == self.department_id
        )

    def clause(self):
        """The same rule as a WHERE clause on System."""
        base = System.tenant_id == self.tenant_id
        if self.all_departments:
            return base
        if self.department_id is None:
            return base & System.department_id.is_(None)
        return base & or_(System.department_id.is_(None), System.department_id == self.department_id)


def scope_for(user: User, *, grants_all: bool = False, tenant_id: int | None = None) -> Scope:
    """
    Tenant Admin sees every department. Everyone else — Org Admin and
    Employee alike — sees their own department and shared systems. Someone
    with no department sees shared systems only, never "everything with no
    department" by accident.

    A Super Admin belongs to no organisation: `tenant_id` names the one they
    are working in, and they see every department of it. For anyone else
    `tenant_id` is ignored — their organisation is their own.
    """
    return Scope(
        tenant_id=tenant_id if user.role == "super_admin" else user.tenant_id,
        all_departments=grants_all or user.role == "tenant_admin",
        department_id=user.dept_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Systems
# ─────────────────────────────────────────────────────────────────────────────


async def _department_names(db: AsyncSession, tenant_id: int | None) -> dict[int, str]:
    rows = (
        await db.execute(
            select(Department.department_id, Department.department_name)
            .where(Department.tenant_id == tenant_id)
        )
    ).all()
    return {i: n for i, n in rows}


def _system_out(s: System, names: dict[int, str]) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "kind": s.kind,
        "environment": s.environment,
        "description": s.description,
        "department_id": s.department_id,
        # None means shared. Spelled out so the UI never has to guess.
        "department_name": names.get(s.department_id) if s.department_id else None,
    }


async def list_systems(db: AsyncSession, *, scope: Scope) -> list[dict]:
    """Systems this person can see, with how many credentials each depends on."""
    rows = (
        await db.execute(
            select(System, func.count(CredentialDependency.id))
            .outerjoin(CredentialDependency, CredentialDependency.system_id == System.id)
            .where(scope.clause())
            .group_by(System.id)
            .order_by(System.name)
        )
    ).all()
    names = await _department_names(db, scope.tenant_id)
    return [{**_system_out(s, names), "credential_count": n} for s, n in rows]


async def assignable_departments(db: AsyncSession, *, scope: Scope) -> list[dict]:
    """Departments this person may put a system in. Shared is always allowed."""
    q = select(Department.department_id, Department.department_name).where(
        Department.tenant_id == scope.tenant_id
    )
    if not scope.all_departments:
        if scope.department_id is None:
            return []
        q = q.where(Department.department_id == scope.department_id)
    rows = (await db.execute(q.order_by(Department.department_name))).all()
    return [{"id": i, "name": n} for i, n in rows]


async def get_visible_system(db: AsyncSession, *, scope: Scope, system_id: int) -> System:
    system = (
        await db.execute(select(System).where(System.id == system_id, scope.clause()))
    ).scalars().first()
    if not system:
        # Same answer for "no such system" and "another department's".
        raise HTTPException(404, "System not found.")
    return system


async def upsert_system(
    db: AsyncSession, *, ctx, scope: Scope, name: str, kind: str | None,
    environment: str | None, description: str | None = None,
    department_id: int | None = None, department_given: bool = False,
) -> System:
    """
    Find or create, among the systems this person can see.

    Upsert rather than create because the natural flow is "link this credential
    to production-postgres" — and the user should not have to know whether that
    system already exists. Matching only within what they can see means linking
    never quietly attaches a credential to another department's system.

    A new system lands in the creator's department. A Tenant Admin may say
    which department (or shared) via `department_id`; without one, their new
    systems are shared, since they belong to no department themselves.
    """
    name = name.strip()

    if department_given:
        target = await _check_target_department(db, scope=scope, department_id=department_id)
    else:
        target = None if scope.all_departments else scope.department_id

    q = select(System).where(
        scope.clause(),
        System.name == name,
        System.environment == environment if environment is not None else System.environment.is_(None),
    )
    candidates = (await db.execute(q)).scalars().all()
    # Prefer the one in the intended department, then a shared one.
    for want in (target, None):
        for s in candidates:
            if s.department_id == want:
                return s
    if candidates and not department_given:
        return candidates[0]

    system = System(
        tenant_id=scope.tenant_id,
        name=name,
        kind=kind,
        environment=environment,
        description=description,
        department_id=target,
    )
    db.add(system)
    await db.flush()

    await audit.record(
        db, action="system.created", target_type="system", target_id=system.id,
        details={"name": name, "environment": environment, "department_id": target},
        **ctx.audit_kwargs(),
    )
    return system


async def _check_target_department(
    db: AsyncSession, *, scope: Scope, department_id: int | None
) -> int | None:
    """
    May this person put a system in `department_id`? None (shared) always.
    A Tenant Admin, any department in the organisation; anyone else, only
    their own.
    """
    if department_id is None:
        return None
    if not scope.all_departments and department_id != scope.department_id:
        raise HTTPException(403, "You can only use your own department, or shared.")
    exists = (
        await db.execute(
            select(Department.department_id).where(
                Department.department_id == department_id,
                Department.tenant_id == scope.tenant_id,
            )
        )
    ).first()
    if not exists:
        raise HTTPException(404, "Department not found.")
    return department_id


async def move_system(
    db: AsyncSession, *, ctx, scope: Scope, system_id: int, department_id: int | None
) -> System:
    """
    Put a system in a department, or make it shared.

    The system must be one you can see, and the destination one you may use:
    a Tenant Admin anywhere in the organisation; an Org Admin between their
    own department and shared. So an Org Admin can share their system with
    everyone, or claim a shared one — never move one into or out of another
    department.
    """
    system = await get_visible_system(db, scope=scope, system_id=system_id)
    target = await _check_target_department(db, scope=scope, department_id=department_id)
    if system.department_id == target:
        return system

    # The rename-on-move collision: the destination already has a system with
    # this name and environment. Say so instead of surfacing an integrity error.
    clash = (
        await db.execute(
            select(System.id).where(
                System.tenant_id == system.tenant_id,
                System.id != system.id,
                System.name == system.name,
                (System.environment == system.environment) if system.environment is not None
                else System.environment.is_(None),
                (System.department_id == target) if target is not None
                else System.department_id.is_(None),
            )
        )
    ).first()
    if clash:
        raise HTTPException(
            409,
            f"That department already has a system called “{system.name}”"
            + (f" in {system.environment}" if system.environment else "") + ".",
        )

    before = system.department_id
    system.department_id = target
    await audit.record(
        db, action="system.department_changed", target_type="system", target_id=system.id,
        details={"name": system.name, "from": before, "to": target},
        **ctx.audit_kwargs(),
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


async def get_dependency(
    db: AsyncSession, *, scope: Scope, dependency_id: int
) -> tuple[CredentialDependency, Credential]:
    """
    A link, if its credential is in this organisation and its system is one
    this person can see. 404 otherwise.

    Previously `unlink` fetched by id alone — anyone with credential.edit could
    delete any link in any organisation by counting upwards.
    """
    row = (
        await db.execute(
            select(CredentialDependency, Credential)
            .join(Credential, Credential.id == CredentialDependency.credential_id)
            .join(System, System.id == CredentialDependency.system_id)
            .where(
                CredentialDependency.id == dependency_id,
                Credential.tenant_id == scope.tenant_id,
                Credential.deleted_at.is_(None),
                scope.clause(),
            )
        )
    ).first()
    if not row:
        raise HTTPException(404, "Dependency not found.")
    return row[0], row[1]


async def unlink(db: AsyncSession, *, ctx, dependency: CredentialDependency) -> None:
    await db.delete(dependency)
    await audit.record(
        db, action="dependency.unlinked", target_type="credential",
        target_id=dependency.credential_id, details={"system_id": dependency.system_id},
        **ctx.audit_kwargs(),
    )


async def for_credential(db: AsyncSession, credential_id: int, *, scope: Scope) -> dict:
    """
    The systems this credential feeds that this person can see, and how many
    more there are elsewhere — a count, not names, so the total is honest
    without revealing another department's systems.
    """
    rows = (
        await db.execute(
            select(CredentialDependency, System)
            .join(System, System.id == CredentialDependency.system_id)
            .where(CredentialDependency.credential_id == credential_id)
            .order_by(System.name)
        )
    ).all()
    names = await _department_names(db, scope.tenant_id)
    visible = [(d, s) for d, s in rows if scope.sees(s)]
    return {
        "dependencies": [
            {
                "dependency_id": d.id,
                "system_id": s.id,
                "name": s.name,
                "kind": s.kind,
                "environment": s.environment,
                "department_id": s.department_id,
                "department_name": names.get(s.department_id) if s.department_id else None,
                "notes": d.notes,
            }
            for d, s in visible
        ],
        "in_other_departments": len(rows) - len(visible),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Blast radius
# ─────────────────────────────────────────────────────────────────────────────


async def impact_of(
    db: AsyncSession, *, credential: Credential, action: str = "rotate",
    scope: Scope | None = None,
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

    Every system is listed, in every department — see the module docstring.
    Those outside the caller's departments carry `other_department: true`.
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
            "other_department": bool(scope) and not scope.sees(system),
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


# ─────────────────────────────────────────────────────────────────────────────
# The map
# ─────────────────────────────────────────────────────────────────────────────


def _reachable_credentials(user: User):
    """Credential ids this person owns or holds a live share on."""
    now = datetime.now(timezone.utc)
    team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    shared = select(Share.credential_id).where(
        Share.status == "active",
        or_(Share.grantee_user_id == user.id, Share.grantee_team_id.in_(team_ids)),
        or_(Share.starts_at.is_(None), Share.starts_at <= now),
        or_(Share.expires_at.is_(None), Share.expires_at > now),
    )
    return or_(Credential.owner_id == user.id, Credential.id.in_(shared))


async def org_graph(db: AsyncSession, *, scope: Scope, user: User) -> dict:
    """
    The map, as this person may see it: nodes and edges.

    Bipartite by nature — credentials on one side, systems on the other, edges
    only between them. That shape is what makes it renderable as two columns
    rather than needing a force-directed layout.

    Systems: those in scope. Edges: those ending at a system in scope.
    Credentials: for a Tenant Admin, all of them; for everyone else, those on
    a visible edge plus their own and shared-with-them ones — so the unmapped
    warning still covers what they hold, without listing every credential in
    the company.
    """
    names = await _department_names(db, scope.tenant_id)

    systems = (
        await db.execute(select(System).where(scope.clause()).order_by(System.name))
    ).scalars().all()
    visible_system_ids = {s.id for s in systems}

    all_edges = (
        await db.execute(
            select(CredentialDependency.credential_id, CredentialDependency.system_id)
            .join(Credential, Credential.id == CredentialDependency.credential_id)
            .where(Credential.tenant_id == scope.tenant_id, Credential.deleted_at.is_(None))
        )
    ).all()
    edges = [(c, s) for c, s in all_edges if s in visible_system_ids]

    q = select(Credential.id, Credential.name, Credential.kind).where(
        Credential.tenant_id == scope.tenant_id, Credential.deleted_at.is_(None)
    )
    if not scope.all_departments:
        on_visible_edge = {c for c, _ in edges}
        q = q.where(or_(Credential.id.in_(sorted(on_visible_edge) or [-1]),
                        _reachable_credentials(user)))
    creds = (await db.execute(q.order_by(Credential.name))).all()

    # "Unmapped" means linked to nothing anywhere — not "linked to nothing you
    # can see". A credential feeding only another department's system is
    # mapped; calling it unmapped would send someone looking for a problem
    # that isn't there.
    mapped_anywhere = {c for c, _ in all_edges}
    linked_systems = {s for _, s in edges}
    unmapped = sum(1 for cid, _n, _k in creds if cid not in mapped_anywhere)

    return {
        "scope": {
            "all_departments": scope.all_departments,
            "department_id": scope.department_id,
            "department_name": names.get(scope.department_id) if scope.department_id else None,
        },
        "credentials": [
            {
                "id": cid, "name": name, "kind": kind,
                # Surfaced rather than hidden: an unmapped credential is not a
                # safe one, it is one whose blast radius is unknown.
                "unmapped": cid not in mapped_anywhere,
            }
            for cid, name, kind in creds
        ],
        "systems": [
            {**_system_out(s, names), "orphaned": s.id not in linked_systems}
            for s in systems
        ],
        "edges": [{"credential_id": c, "system_id": s} for c, s in edges],
        "stats": {
            "credentials": len(creds),
            "systems": len(systems),
            "links": len(edges),
            "unmapped_credentials": unmapped,
        },
    }
