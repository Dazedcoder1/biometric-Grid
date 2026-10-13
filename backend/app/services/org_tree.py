"""
The organisation hierarchy, built from the database for whoever is asking.

    Super Admin               every organisation (departments load on expand)
    Organisation Admin        their organisation: admins, departments, people
      (tenant_admin)
    Department Admin          their department, with who they report to
      (org_admin)
    Employee                  themselves and who they report to

Nothing here is cached or hardcoded: every call reads the current rows, so a
new department, a transfer or a replaced admin shows on the next load.

"Exactly one admin" is a rule the write paths enforce (routes/org_tree.py:
assigning an admin replaces the previous one). Data from before the rule can
still break it, so every organisation and department also carries
`warnings` — no admin, or more than one — for an administrator to fix.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select

from app.models.domain import Department, Tenant, User
from app.services.oversight_service import can_oversee

ROLE_LABEL = {
    "super_admin": "Super Admin",
    "tenant_admin": "Organisation Admin",
    "org_admin": "Department Admin",
    "employee": "Employee",
}
STAFF = ("tenant_admin", "org_admin", "employee")


def initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def person(u: User, viewer: User) -> dict:
    return {
        "id": u.id, "name": u.name, "email": u.email, "employee_code": u.employee_code,
        "role": u.role, "role_label": ROLE_LABEL.get(u.role, u.role), "dept_id": u.dept_id,
        "tenant_id": u.tenant_id, "is_active": u.is_active, "is_hr": bool(getattr(u, "is_hr", False)),
        "initials": initials(u.name), "is_me": u.id == viewer.id,
        # The same rule the reset endpoint enforces; the tree only shows the
        # button where the server would accept the request.
        "can_reset": can_oversee(viewer, u, u.tenant_id),
    }


def scope_of(viewer: User) -> str:
    if viewer.role == "super_admin":
        return "platform"
    if viewer.role == "tenant_admin" and viewer.tenant_id:
        return "organisation"
    if viewer.role == "org_admin" and viewer.dept_id:
        return "department"
    return "self"


def can_manage_org(viewer: User, tenant_id: int | None) -> bool:
    """Create departments, assign Department Admins, move people."""
    if tenant_id is None:
        return False
    if viewer.role == "super_admin":
        return True
    return viewer.role == "tenant_admin" and viewer.tenant_id == tenant_id


def can_view_org(viewer: User, tenant_id: int) -> bool:
    return viewer.role == "super_admin" or (viewer.role == "tenant_admin" and viewer.tenant_id == tenant_id)


def _dept_warnings(admins: list) -> list[str]:
    if not admins:
        return ["No Department Admin"]
    if len(admins) > 1:
        return [f"{len(admins)} Department Admins — there should be one"]
    return []


def _org_warnings(admins: list) -> list[str]:
    if not admins:
        return ["No Organisation Admin"]
    if len(admins) > 1:
        return [f"{len(admins)} Organisation Admins — there should be one"]
    return []


async def organisation(db, tenant_id: int, viewer: User) -> dict:
    """One organisation in full: its admins, every department, every person."""
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
    depts = (await db.execute(select(Department).where(
        Department.tenant_id == tenant_id).order_by(Department.department_name))).scalars().all()
    people = (await db.execute(select(User).where(
        User.tenant_id == tenant_id, User.is_active.is_(True), User.role.in_(STAFF)
    ).order_by(User.name))).scalars().all()

    by_dept: dict[int | None, list[User]] = defaultdict(list)
    org_admins = []
    for u in people:
        if u.role == "tenant_admin":
            org_admins.append(u)
        else:
            by_dept[u.dept_id].append(u)

    known = {d.department_id for d in depts}
    departments = []
    for d in depts:
        members = by_dept.get(d.department_id, [])
        admins = [u for u in members if u.role == "org_admin"]
        employees = [u for u in members if u.role != "org_admin"]
        if not d.is_active and not members:
            continue
        departments.append({
            "type": "department", "id": d.department_id, "name": d.department_name, "is_active": d.is_active,
            "tenant_id": tenant_id,
            "admins": [person(u, viewer) for u in admins],
            "employees": [person(u, viewer) for u in employees],
            "count": len(members),
            "warnings": _dept_warnings(admins) if d.is_active else ["Inactive department"],
        })
    unassigned = [u for dept_id, us in by_dept.items() if dept_id not in known for u in us]

    return {
        "type": "organisation", "id": tenant_id, "name": tenant.name if tenant else f"#{tenant_id}",
        "admins": [person(u, viewer) for u in org_admins],
        "departments": departments,
        "unassigned": [person(u, viewer) for u in unassigned],
        "count": len(people),
        "warnings": _org_warnings(org_admins),
        "can_manage": can_manage_org(viewer, tenant_id),
        "can_assign_org_admin": viewer.role == "super_admin",
    }


async def platform(db, viewer: User) -> dict:
    """Every organisation, summarised. Each one's detail loads on expand."""
    tenants = (await db.execute(select(Tenant).order_by(Tenant.name))).scalars().all()
    counts = dict((await db.execute(
        select(User.tenant_id, func.count(User.id)).where(
            User.is_active.is_(True), User.role.in_(STAFF)).group_by(User.tenant_id))).all())
    dept_counts = dict((await db.execute(
        select(Department.tenant_id, func.count(Department.department_id)).where(
            Department.is_active.is_(True)).group_by(Department.tenant_id))).all())
    admins = (await db.execute(select(User).where(
        User.role == "tenant_admin", User.is_active.is_(True)).order_by(User.name))).scalars().all()
    admins_by: dict[int, list[User]] = defaultdict(list)
    for a in admins:
        admins_by[a.tenant_id].append(a)
    return {
        "type": "platform", "name": "All organisations",
        "organisations": [{
            "type": "organisation", "id": t.id, "name": t.name,
            "admins": [person(a, viewer) for a in admins_by.get(t.id, [])],
            "count": counts.get(t.id, 0), "departments_count": dept_counts.get(t.id, 0),
            "warnings": _org_warnings(admins_by.get(t.id, [])),
            "can_manage": True, "can_assign_org_admin": True, "loaded": False,
        } for t in tenants],
    }


async def department_view(db, viewer: User) -> dict:
    """A Department Admin: their department, and who they report to."""
    d = (await db.execute(select(Department).where(Department.department_id == viewer.dept_id))).scalars().first()
    tenant = (await db.execute(select(Tenant).where(Tenant.id == viewer.tenant_id))).scalars().first()
    members = (await db.execute(select(User).where(
        User.tenant_id == viewer.tenant_id, User.dept_id == viewer.dept_id, User.is_active.is_(True),
        User.role.in_(("org_admin", "employee"))).order_by(User.name))).scalars().all()
    org_admins = (await db.execute(select(User).where(
        User.tenant_id == viewer.tenant_id, User.role == "tenant_admin", User.is_active.is_(True)))).scalars().all()
    admins = [u for u in members if u.role == "org_admin"]
    return {
        "type": "organisation", "id": viewer.tenant_id, "name": tenant.name if tenant else "",
        "admins": [person(u, viewer) for u in org_admins],
        "departments": [{
            "type": "department", "id": viewer.dept_id, "name": d.department_name if d else "My department",
            "tenant_id": viewer.tenant_id, "is_active": bool(d and d.is_active),
            "admins": [person(u, viewer) for u in admins],
            "employees": [person(u, viewer) for u in members if u.role != "org_admin"],
            "count": len(members), "warnings": _dept_warnings(admins),
        }],
        "unassigned": [], "count": len(members), "warnings": [],
        "can_manage": False, "can_assign_org_admin": False, "partial": True,
    }


async def self_view(db, viewer: User) -> dict:
    """An employee: themselves, their Department Admin, their Organisation Admin."""
    tenant = (await db.execute(select(Tenant).where(Tenant.id == viewer.tenant_id))).scalars().first() \
        if viewer.tenant_id else None
    d = (await db.execute(select(Department).where(Department.department_id == viewer.dept_id))).scalars().first() \
        if viewer.dept_id else None
    dept_admins = (await db.execute(select(User).where(
        User.tenant_id == viewer.tenant_id, User.dept_id == viewer.dept_id, User.role == "org_admin",
        User.is_active.is_(True)))).scalars().all() if viewer.dept_id else []
    org_admins = (await db.execute(select(User).where(
        User.tenant_id == viewer.tenant_id, User.role == "tenant_admin", User.is_active.is_(True)))).scalars().all() \
        if viewer.tenant_id else []
    return {
        "type": "organisation", "id": viewer.tenant_id, "name": tenant.name if tenant else "",
        "admins": [person(u, viewer) for u in org_admins],
        "departments": [{
            "type": "department", "id": viewer.dept_id, "name": d.department_name if d else "No department",
            "tenant_id": viewer.tenant_id, "is_active": True,
            "admins": [person(u, viewer) for u in dept_admins if u.id != viewer.id],
            "employees": [person(viewer, viewer)] if viewer.role != "org_admin" else [],
            "count": 1, "warnings": [],
        }],
        "unassigned": [], "count": 1, "warnings": [],
        "can_manage": False, "can_assign_org_admin": False, "partial": True,
    }


async def tree_for(db, viewer: User) -> dict:
    scope = scope_of(viewer)
    if scope == "platform":
        root = await platform(db, viewer)
    elif scope == "organisation":
        root = await organisation(db, viewer.tenant_id, viewer)
    elif scope == "department":
        root = await department_view(db, viewer)
    else:
        root = await self_view(db, viewer)
    return {"scope": scope, "root": root}


def in_scope(viewer: User, target: User) -> bool:
    """May the viewer see this person at all (search, profile)?"""
    if target.id == viewer.id:
        return True
    if target.role == "super_admin":
        return viewer.role == "super_admin"
    scope = scope_of(viewer)
    if scope == "platform":
        return True
    if scope == "organisation":
        return target.tenant_id == viewer.tenant_id
    if scope == "department":
        return target.tenant_id == viewer.tenant_id and (
            target.dept_id == viewer.dept_id or target.role == "tenant_admin")
    # An employee sees the admins they report to.
    return target.tenant_id == viewer.tenant_id and (
        target.role == "tenant_admin" or (target.role == "org_admin" and target.dept_id == viewer.dept_id))
