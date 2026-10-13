"""
Organisation hierarchy — /api/org-tree.

    GET  /                        the tree, scoped to whoever asks
    GET  /orgs/{tenant_id}        one organisation in full (Super Admin, or its own Organisation Admin)
    GET  /search?q=               people within the caller's scope
    GET  /people/{user_id}        a person's details and what the caller may do to them
    POST /departments             add a department                 Super Admin / Organisation Admin
    POST /departments/{id}/admin  make someone its Department Admin — replaces the current one
    POST /orgs/{tenant_id}/admin  make someone its Organisation Admin — Super Admin only; replaces
    POST /people/{id}/move        move an employee to another department

Password resets use the existing POST /api/accounts/{id}/reset-password,
which applies the same hierarchy (oversight_service.can_oversee): temporary
password, forced change at next sign-in, every session signed out, audited.

"Exactly one admin": assigning a Department Admin or Organisation Admin
demotes whoever held that seat to an ordinary employee — account, history
and department kept. Every change is in the audit log and the people
affected are notified.

All checks are made here, on the server. The tree only hides buttons the
server would refuse anyway; a request for someone outside the caller's scope
gets the same 404 as a request for someone who does not exist.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core import activity
from app.db.session import get_db
from app.models.domain import Department, Tenant, User
from app.services import notification_service
from app.services import org_tree as T
from app.services.oversight_service import can_oversee

router = APIRouter()


async def _tenant(db, tenant_id: int) -> Tenant:
    t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
    if not t:
        raise HTTPException(404, "Organisation not found.")
    return t


async def _visible_person(db, viewer: User, user_id: int) -> User:
    u = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not u or not T.in_scope(viewer, u):
        raise HTTPException(404, "Person not found.")
    return u


async def _dept(db, dept_id: int) -> Department:
    d = (await db.execute(select(Department).where(Department.department_id == dept_id))).scalars().first()
    if not d:
        raise HTTPException(404, "Department not found.")
    return d


async def _notify(db, tenant_id, actor, user_ids, title, message, entity_id=None):
    ids = [i for i in user_ids if i and i != actor.id]
    if ids:
        await notification_service.create_notifications_for_recipients(
            db, tenant_id=tenant_id, actor_id=actor.id, recipient_ids=ids, event_type="org_change",
            title=title, message=message, entity_type="user", entity_id=entity_id,
        )


# ─── reading ─────────────────────────────────────────────────────────────────

@router.get("")
async def tree(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await T.tree_for(db, current_user)


@router.get("/orgs/{tenant_id}")
async def organisation(tenant_id: int, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if not T.can_view_org(current_user, tenant_id):
        raise HTTPException(404, "Organisation not found.")
    await _tenant(db, tenant_id)
    return await T.organisation(db, tenant_id, current_user)


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=80),
                 current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """People matching name, email or employee code — only within the caller's scope."""
    scope = T.scope_of(current_user)
    term = f"%{q.strip().lower()}%"
    stmt = select(User).where(
        User.is_active.is_(True), User.role.in_(T.STAFF),
        or_(func.lower(User.name).like(term), func.lower(User.email).like(term),
            func.lower(func.coalesce(User.employee_code, "")).like(term)),
    )
    if scope == "organisation":
        stmt = stmt.where(User.tenant_id == current_user.tenant_id)
    elif scope == "department":
        stmt = stmt.where(User.tenant_id == current_user.tenant_id, User.dept_id == current_user.dept_id)
    elif scope == "self":
        stmt = stmt.where(User.id == current_user.id)
    rows = (await db.execute(stmt.order_by(User.name).limit(50))).scalars().all()
    rows = [u for u in rows if T.in_scope(current_user, u)]
    tenants = {t.id: t.name for t in (await db.execute(select(Tenant).where(
        Tenant.id.in_({u.tenant_id for u in rows} or {0})))).scalars().all()}
    depts = {d.department_id: d.department_name for d in (await db.execute(select(Department).where(
        Department.department_id.in_({u.dept_id for u in rows if u.dept_id} or {0})))).scalars().all()}
    return [{**T.person(u, current_user), "organisation": tenants.get(u.tenant_id),
             "department": depts.get(u.dept_id)} for u in rows]


@router.get("/people/{user_id}")
async def profile(user_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    u = await _visible_person(db, current_user, user_id)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == u.tenant_id))).scalars().first() if u.tenant_id else None
    dept = (await db.execute(select(Department).where(Department.department_id == u.dept_id))).scalars().first() \
        if u.dept_id else None
    reports_to = []
    if u.role in ("employee",) and u.dept_id:
        reports_to += (await db.execute(select(User).where(
            User.tenant_id == u.tenant_id, User.dept_id == u.dept_id, User.role == "org_admin",
            User.is_active.is_(True)))).scalars().all()
    if u.role in ("employee", "org_admin") and u.tenant_id:
        reports_to += (await db.execute(select(User).where(
            User.tenant_id == u.tenant_id, User.role == "tenant_admin", User.is_active.is_(True)))).scalars().all()
    manage = T.can_manage_org(current_user, u.tenant_id)
    departments = []
    if manage:
        departments = [{"id": d.department_id, "name": d.department_name} for d in (await db.execute(
            select(Department).where(Department.tenant_id == u.tenant_id, Department.is_active.is_(True))
            .order_by(Department.department_name))).scalars().all()]
    return {
        **T.person(u, current_user),
        "organisation": tenant.name if tenant else None,
        "department": dept.department_name if dept else None,
        "created_at": u.created_at, "fingerprint_enrolled": u.finger_id is not None,
        "must_change_password": bool(u.must_change_password),
        "reports_to": [T.person(x, current_user) for x in reports_to if x.id != u.id],
        "actions": {
            "reset_password": can_oversee(current_user, u, u.tenant_id),
            "make_department_admin": manage and u.role in ("employee", "org_admin") and u.dept_id is not None
                                     and u.id != current_user.id,
            "make_organisation_admin": current_user.role == "super_admin" and u.role in ("employee", "org_admin"),
            "move": manage and u.role == "employee" and u.id != current_user.id,
        },
        "departments": departments,
    }


# ─── changing ────────────────────────────────────────────────────────────────

class DepartmentIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    tenant_id: int | None = None          # Super Admin names the organisation


@router.post("/departments", status_code=201)
async def add_department(data: DepartmentIn, request: Request, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    tenant_id = data.tenant_id if current_user.role == "super_admin" else current_user.tenant_id
    if not T.can_manage_org(current_user, tenant_id):
        raise HTTPException(403, "Only the Super Admin or this organisation's admin can add departments.")
    await _tenant(db, tenant_id)
    name = data.name.strip()
    clash = (await db.execute(select(Department).where(
        Department.tenant_id == tenant_id, func.lower(Department.department_name) == name.lower(),
        Department.is_active.is_(True)))).scalars().first()
    if clash:
        raise HTTPException(409, f"There is already a department called {clash.department_name}.")
    d = Department(tenant_id=tenant_id, department_name=name, is_active=True)
    db.add(d)
    await db.flush()
    await activity.log(db, request, action="department.created", tenant_id=tenant_id, target_type="department",
                       target_id=d.department_id, actor=current_user, details={"name": name, "via": "org_tree"})
    await db.commit()
    return {"id": d.department_id, "name": d.department_name, "tenant_id": tenant_id}


class AssignIn(BaseModel):
    user_id: int


@router.post("/departments/{dept_id}/admin")
async def assign_department_admin(dept_id: int, data: AssignIn, request: Request,
                                  current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    d = await _dept(db, dept_id)
    if not T.can_manage_org(current_user, d.tenant_id):
        raise HTTPException(404, "Department not found.")
    if not d.is_active:
        raise HTTPException(409, "This department is inactive.")
    person = (await db.execute(select(User).where(User.id == data.user_id, User.tenant_id == d.tenant_id))).scalars().first()
    if not person or not person.is_active:
        raise HTTPException(404, "Person not found in this organisation.")
    if person.role not in ("employee", "org_admin"):
        raise HTTPException(409, "Only an employee or a Department Admin can be made a Department Admin.")
    if person.role == "org_admin" and person.dept_id == dept_id:
        return {"message": f"{person.name} is already this department's admin.", "replaced": []}

    left_behind = person.dept_id if person.role == "org_admin" and person.dept_id != dept_id else None
    previous = (await db.execute(select(User).where(
        User.tenant_id == d.tenant_id, User.dept_id == dept_id, User.role == "org_admin",
        User.id != person.id))).scalars().all()
    for p in previous:
        p.role = "employee"                     # one admin per department: the seat changes hands
    from_dept = person.dept_id
    person.role = "org_admin"
    person.dept_id = dept_id

    await activity.log(db, request, action="department.admin_assigned", tenant_id=d.tenant_id,
                       target_type="user", target_id=person.id, actor=current_user,
                       details={"department": d.department_name, "name": person.name,
                                "replaced": [p.name for p in previous], "from_department_id": from_dept})
    await _notify(db, d.tenant_id, current_user, [person.id], f"You are now Department Admin of {d.department_name}",
                  "Your menu updates within the hour, or sign out and back in to see it now.", person.id)
    await _notify(db, d.tenant_id, current_user, [p.id for p in previous],
                  f"{person.name} is now Department Admin of {d.department_name}",
                  "You remain in the department as an employee.", person.id)
    await db.commit()
    msg = f"{person.name} is now Department Admin of {d.department_name}."
    if previous:
        msg += " Replaced: " + ", ".join(p.name for p in previous) + "."
    if left_behind:
        msg += " Their previous department no longer has an admin."
    return {"message": msg, "replaced": [p.id for p in previous], "left_without_admin": left_behind}


@router.post("/orgs/{tenant_id}/admin")
async def assign_organisation_admin(tenant_id: int, data: AssignIn, request: Request,
                                    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role != "super_admin":
        raise HTTPException(403, "Only the Super Admin can assign an Organisation Admin.")
    t = await _tenant(db, tenant_id)
    person = (await db.execute(select(User).where(User.id == data.user_id, User.tenant_id == tenant_id))).scalars().first()
    if not person or not person.is_active:
        raise HTTPException(404, "Person not found in this organisation.")
    if person.role == "tenant_admin":
        return {"message": f"{person.name} is already this organisation's admin.", "replaced": []}
    if person.role not in ("employee", "org_admin"):
        raise HTTPException(409, "Only an employee or a Department Admin can be made Organisation Admin.")

    left_behind = person.dept_id if person.role == "org_admin" else None
    previous = (await db.execute(select(User).where(
        User.tenant_id == tenant_id, User.role == "tenant_admin", User.id != person.id))).scalars().all()
    for p in previous:
        p.role = "employee"
    person.role = "tenant_admin"

    await activity.log(db, request, action="organisation.admin_assigned", tenant_id=tenant_id,
                       target_type="user", target_id=person.id, actor=current_user,
                       details={"organisation": t.name, "name": person.name, "replaced": [p.name for p in previous]})
    await _notify(db, tenant_id, current_user, [person.id], f"You are now the Organisation Admin of {t.name}",
                  "Your menu updates within the hour, or sign out and back in to see it now.", person.id)
    await _notify(db, tenant_id, current_user, [p.id for p in previous], f"{person.name} is now Organisation Admin",
                  "You remain in the organisation as an employee.", person.id)
    await db.commit()
    msg = f"{person.name} is now the Organisation Admin of {t.name}."
    if previous:
        msg += " Replaced: " + ", ".join(p.name for p in previous) + "."
    if left_behind:
        msg += " Their department no longer has a Department Admin."
    return {"message": msg, "replaced": [p.id for p in previous], "left_without_admin": left_behind}


class MoveIn(BaseModel):
    dept_id: int


@router.post("/people/{user_id}/move")
async def move_person(user_id: int, data: MoveIn, request: Request,
                      current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    person = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not person or not T.can_manage_org(current_user, person.tenant_id):
        raise HTTPException(404, "Person not found.")
    if person.id == current_user.id:
        raise HTTPException(400, "You cannot move yourself.")
    if person.role != "employee":
        raise HTTPException(409, "Only employees are moved. To move an admin, make someone else the admin first.")
    d = await _dept(db, data.dept_id)
    if d.tenant_id != person.tenant_id or not d.is_active:
        raise HTTPException(422, "Choose an active department in the same organisation.")
    if person.dept_id == d.department_id:
        return {"message": f"{person.name} is already in {d.department_name}."}
    from_dept = person.dept_id
    person.dept_id = d.department_id
    await activity.log(db, request, action="user.transferred", tenant_id=person.tenant_id, target_type="user",
                       target_id=person.id, actor=current_user,
                       details={"name": person.name, "from_department_id": from_dept, "to": d.department_name})
    admins = (await db.execute(select(User.id).where(
        User.tenant_id == person.tenant_id, User.role == "org_admin",
        User.dept_id.in_([x for x in (from_dept, d.department_id) if x])))).scalars().all()
    await _notify(db, person.tenant_id, current_user, [person.id, *admins],
                  f"{person.name} moved to {d.department_name}", "Department change recorded.", person.id)
    await db.commit()
    return {"message": f"{person.name} moved to {d.department_name}."}
