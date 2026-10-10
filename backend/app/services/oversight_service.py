"""
Who an administrator may look after: whose vault they can open, whose sign-in
password they can reset.

One rule, used by every route that acts on another person, so the people list,
the reveal and the password reset cannot disagree about who is in reach:

    Super Admin   ->  everyone in the organisation they are working in,
                      Tenant Admins included
    Tenant Admin  ->  Org Admins and Employees in their own organisation
    Org Admin     ->  Employees in their own department
    anyone else   ->  nobody

Below the Super Admin it is strictly downward: never a peer — a Tenant Admin
cannot open another Tenant Admin's vault — and never upward. Never across
organisations for anyone: a Super Admin reaches everyone, but one organisation
at a time, the one named by X-Acting-Tenant-Id (deps_security._acting_tenant).

The role check that gets someone to these routes at all (credential.oversee,
user.password_reset) lives in the permission catalogue. This module answers
the separate question of *which people*, which a permission cannot express.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credentials import Credential
from app.models.domain import Department, User

#: Which roles each administrator role reaches.
REACHES: dict[str, frozenset[str]] = {
    # The platform operator: full control, inside one organisation at a time.
    "super_admin": frozenset({"tenant_admin", "org_admin", "employee"}),
    "tenant_admin": frozenset({"org_admin", "employee"}),
    "org_admin": frozenset({"employee"}),
}


def _org(admin: User, tenant_id: int | None) -> int | None:
    """
    The organisation this admin acts in. A Super Admin's comes from the
    request (they have none of their own); everyone else's is their own, and
    anything passed in is ignored — their scope is fixed by their account.
    """
    if admin.role == "super_admin":
        return tenant_id
    return admin.tenant_id


def can_oversee(admin: User, target: User, tenant_id: int | None = None) -> bool:
    """
    May `admin` act on `target`? Pure, so it can be tested without a database.

    Yourself is not "overseen" — your own vault and password go through the
    ordinary routes — so this is False for admin == target.
    """
    if admin.id == target.id:
        return False
    org = _org(admin, tenant_id)
    if org is None or target.tenant_id != org:
        return False
    reachable = REACHES.get(admin.role)
    if not reachable or target.role not in reachable:
        return False
    if admin.role == "org_admin":
        # An Org Admin with no department reaches nobody, rather than everyone
        # whose dept_id is also NULL.
        return admin.dept_id is not None and target.dept_id == admin.dept_id
    return True


def _scope_query(admin: User, tenant_id: int | None = None):
    """Users this admin reaches, as a query. Mirrors can_oversee exactly."""
    reachable = REACHES.get(admin.role)
    org = _org(admin, tenant_id)
    if org is None or not reachable:
        return None
    q = select(User).where(
        User.tenant_id == org,
        User.role.in_(tuple(reachable)),
        User.id != admin.id,
    )
    if admin.role == "org_admin":
        if admin.dept_id is None:
            return None
        q = q.where(User.dept_id == admin.dept_id)
    return q


#: Order on the People list: most senior first.
_ROLE_ORDER = {"tenant_admin": 0, "org_admin": 1, "employee": 2}


async def people(db: AsyncSession, admin: User, tenant_id: int | None = None) -> list[dict]:
    """
    The admin themselves first (when they belong to this organisation), then
    everyone they reach, with how many credentials each holds. Inactive
    accounts are included on purpose: offboarding someone is the most common
    reason to look in their vault.
    """
    owned = (
        select(Credential.owner_id, func.count(Credential.id).label("n"))
        .where(Credential.deleted_at.is_(None))
        .group_by(Credential.owner_id)
        .subquery()
    )

    def with_counts(q):
        return (
            q.add_columns(
                func.coalesce(owned.c.n, 0).label("credential_count"),
                Department.department_name,
            )
            .outerjoin(owned, owned.c.owner_id == User.id)
            .outerjoin(Department, Department.department_id == User.dept_id)
        )

    rows = []
    # A Super Admin has no vault of their own in any organisation, so there is
    # no "you" row for them — just the people.
    if admin.tenant_id is not None:
        me = (await db.execute(with_counts(select(User).where(User.id == admin.id)))).first()
        if me:
            rows.append((me, True))

    scope = _scope_query(admin, tenant_id)
    if scope is not None:
        others = (await db.execute(with_counts(scope).order_by(User.name))).all()
        others = sorted(others, key=lambda r: (_ROLE_ORDER.get(r[0].role, 9), (r[0].name or "").lower()))
        rows.extend((r, False) for r in others)

    return [
        {
            "id": r[0].id,
            "name": r[0].name,
            "email": r[0].email,
            "employee_code": r[0].employee_code,
            "role": r[0].role,
            "department": r[2],
            "is_active": bool(r[0].is_active),
            "must_change_password": bool(getattr(r[0], "must_change_password", False)),
            "credential_count": int(r[1] or 0),
            "is_me": is_me,
        }
        for r, is_me in rows
    ]


async def get_overseeable(
    db: AsyncSession, admin: User, user_id: int, tenant_id: int | None = None
) -> User:
    """
    The person, if this admin reaches them. 404 otherwise — the same answer
    for "no such user" and "not yours", so the route cannot be used to learn
    which accounts exist in other departments or organisations.
    """
    target = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not target or not can_oversee(admin, target, tenant_id):
        raise HTTPException(404, "Person not found.")
    return target


async def credentials_of(db: AsyncSession, owner_id: int) -> list[Credential]:
    return list(
        (
            await db.execute(
                select(Credential)
                .where(Credential.owner_id == owner_id, Credential.deleted_at.is_(None))
                .order_by(Credential.name)
            )
        ).scalars().all()
    )
