"""
Platform administration: the organisations on this deployment.

Everything here belongs to the Super Admin, who sits above every organisation
rather than inside one. Four things this module used to get wrong, and why the
replacements look the way they do:

* **Creating an organisation left it unusable.** The request carried a manager
  email and password and then ignored both, producing a tenant with no admin,
  no department and no settings row — nobody could ever sign in to it. Creation
  now provisions the same minimum `create_organisation.py` does, in one
  transaction, so an organisation either exists and works or does not exist.

* **The list handed every tenant's API key to the browser** to draw a list of
  names. Keys now leave this module in exactly two places: once at creation and
  once at rotation, each to the person who just caused it. Everywhere else the
  UI gets the last four characters, which is enough to tell keys apart.

* **Deleting an organisation was one unguarded call.** Most tables reference
  `tenants.id` without ON DELETE, so on any real organisation it failed with an
  integrity error; had it worked, it would have erased a company in a click.
  Deletion is now refused while the organisation holds anything a person put
  there, and the refusal says exactly what — see `_inventory`.

* **None of it was audited.** Every change is written to the hash-chained audit
  log against the affected organisation, so that organisation's own admins can
  see what the platform operator did to it.
"""

from __future__ import annotations

import logging
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_super_admin
from app.core import audit
from app.core.security import hash_password
from app.db.session import get_db
from app.models.domain import Department, Settings, Tenant, User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def new_api_key() -> str:
    """Same shape `create_organisation.py` issues, so keys are interchangeable."""
    return secrets.token_urlsafe(24)


def key_hint(api_key: str | None) -> str | None:
    """Enough of a key to tell two apart, not enough to use one."""
    if not api_key:
        return None
    return f"…{api_key[-4:]}"


def _who(request: Request, actor: User, tenant_id: int) -> dict:
    """
    The audit fields every call here shares.

    The organisation is both the target and the tenant the row is filed under:
    filing it there is what puts it in front of that organisation's own admins.
    Each call site still names its action literally — the audit-label test
    finds actions by scanning for `audit.record(... action="...")`, and a
    wrapper taking the action as a variable would hide them from it.
    """
    return {
        "tenant_id": tenant_id,
        "actor_id": actor.id,
        "actor_role": actor.role,
        "target_type": "organisation",
        "target_id": tenant_id,
        "source_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


async def _get_tenant_or_404(db: AsyncSession, tenant_id: int) -> Tenant:
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalars().first()
    if not tenant:
        raise HTTPException(404, "That organisation does not exist.")
    return tenant


async def _name_taken(db: AsyncSession, name: str, *, except_id: int | None = None) -> bool:
    stmt = select(Tenant.id).where(func.lower(Tenant.name) == name.lower())
    if except_id is not None:
        stmt = stmt.where(Tenant.id != except_id)
    return (await db.execute(stmt)).first() is not None


# One pass over every organisation. Correlated subqueries rather than joins:
# joining users, devices and attendance together multiplies rows and turns
# every count into a product of the others.
_STATS_SQL = """
    SELECT
        t.id,
        (SELECT count(*) FROM departments d WHERE d.tenant_id = t.id)          AS departments,
        (SELECT count(*) FROM users u
            WHERE u.tenant_id = t.id AND u.role = 'employee')                  AS employees,
        (SELECT count(*) FROM users u
            WHERE u.tenant_id = t.id AND u.role = 'org_admin')                 AS org_admins,
        (SELECT count(*) FROM users u
            WHERE u.tenant_id = t.id AND u.role = 'tenant_admin')              AS tenant_admins,
        (SELECT count(*) FROM devices v WHERE v.tenant_id = t.id)              AS devices,
        (SELECT count(*) FROM devices v
            WHERE v.tenant_id = t.id AND v.status = 'online')                  AS devices_online,
        (SELECT max(a.timestamp) FROM attendance_logs a WHERE a.tenant_id = t.id) AS last_activity
    FROM tenants t
"""


async def _stats(db: AsyncSession, tenant_id: int | None = None) -> dict[int, dict]:
    sql = _STATS_SQL + (" WHERE t.id = :tid" if tenant_id is not None else "")
    params = {"tid": tenant_id} if tenant_id is not None else {}
    rows = (await db.execute(text(sql), params)).mappings().all()
    return {
        r["id"]: {
            "departments": r["departments"],
            "employees": r["employees"],
            "org_admins": r["org_admins"],
            "tenant_admins": r["tenant_admins"],
            "devices": r["devices"],
            "devices_online": r["devices_online"],
            "last_activity": r["last_activity"],
        }
        for r in rows
    }


_EMPTY_STATS = {
    "departments": 0, "employees": 0, "org_admins": 0, "tenant_admins": 0,
    "devices": 0, "devices_online": 0, "last_activity": None,
}


def _row(tenant: Tenant, stats: dict | None) -> dict:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "created_at": tenant.created_at,
        "api_key_hint": key_hint(tenant.api_key),
        "stats": stats or dict(_EMPTY_STATS),
    }


# ─────────────────────────────────────────────────────────────────────────────
# What an organisation holds, for the delete guard
# ─────────────────────────────────────────────────────────────────────────────

#: Rows that exist because the organisation exists, not because anyone used it.
#: Creation makes the settings row, a department and the tenant admin; opening
#: the vault makes an empty personal vault; roles may be seeded per tenant.
#: These are removed with the organisation. Order matters: users reference
#: departments, so users go first.
SCAFFOLDING_DELETE_ORDER = ("vaults", "roles", "users", "departments", "settings")

#: History, kept on purpose. The audit log has no foreign key to tenants, and
#: the record that an organisation existed and was deleted outlives it.
HISTORY_TABLES = {"audit_log"}

#: How each table reads in a sentence. Anything unlisted is humanised.
TABLE_NOUNS = {
    "users": "people",
    "attendance_logs": "attendance records",
    "devices": "devices",
    "commands": "device commands",
    "leaves": "leave requests",
    "holidays": "holidays",
    "notifications": "notifications",
    "tasks": "tasks",
    "github_repos": "GitHub repositories",
    "credentials": "vault credentials",
    "shares": "credential shares",
    "teams": "teams",
    "systems": "systems",
    "rotation_policies": "rotation policies",
    "racks": "racks",
}

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


async def _tenant_tables(db: AsyncSession) -> list[str]:
    """
    Every table with a tenant_id column, read from the catalog.

    Read rather than listed so that a table added next month is covered by the
    delete guard without anyone remembering to update it — forgetting would
    mean the guard waves through an organisation that still has data in it.
    """
    rows = (
        await db.execute(text("""
            SELECT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_name = c.table_name AND t.table_schema = c.table_schema
            WHERE c.column_name = 'tenant_id'
              AND c.table_schema = current_schema()
              AND t.table_type = 'BASE TABLE'
            ORDER BY c.table_name
        """))
    ).scalars().all()
    # Catalog names are already safe identifiers; checked anyway, because they
    # are about to be interpolated into SQL.
    return [r for r in rows if _IDENT.match(r)]


async def _inventory(db: AsyncSession, tenant_id: int) -> list[dict]:
    """
    Everything that would stop this organisation being deleted.

    Empty list means safe to delete. Users are the one table split in two: the
    tenant admins are scaffolding, everyone else is people someone added.
    """
    blockers: list[dict] = []
    for table in await _tenant_tables(db):
        if table in HISTORY_TABLES:
            continue
        if table == "users":
            n = (await db.execute(
                text("SELECT count(*) FROM users WHERE tenant_id = :t AND role <> 'tenant_admin'"),
                {"t": tenant_id},
            )).scalar_one()
        elif table in SCAFFOLDING_DELETE_ORDER:
            continue
        else:
            n = (await db.execute(
                text(f'SELECT count(*) FROM "{table}" WHERE tenant_id = :t'),
                {"t": tenant_id},
            )).scalar_one()
        if n:
            blockers.append({
                "table": table,
                "label": TABLE_NOUNS.get(table, table.replace("_", " ")),
                "count": int(n),
            })
    return blockers


def describe_blockers(blockers: list[dict]) -> str:
    parts = [f"{b['count']} {b['label']}" for b in blockers]
    if len(parts) > 1:
        listed = ", ".join(parts[:-1]) + " and " + parts[-1]
    else:
        listed = parts[0]
    return (
        f"This organisation still holds {listed}. Only an empty organisation can "
        "be deleted, so nothing anyone entered is lost by one click. Remove "
        "those first, or leave the organisation in place."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

def _clean(value: str) -> str:
    value = " ".join((value or "").split())
    if not value:
        raise ValueError("cannot be blank")
    return value


class OrganisationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    admin_name: str = Field(..., min_length=1, max_length=120)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8, max_length=128)
    department: str = Field("General", min_length=1, max_length=80)

    @field_validator("name", "admin_name", "department")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _clean(v)

    @field_validator("admin_email")
    @classmethod
    def _lower(cls, v: str) -> str:
        # Sign-in compares emails exactly. Storing them lower-case is what
        # stops "Admin@Acme.com" and "admin@acme.com" becoming two accounts.
        return str(v).strip().lower()

    @field_validator("admin_password")
    @classmethod
    def _strong_enough(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("must contain at least one letter and one number")
        return v


class OrganisationRename(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _clean(v)


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/overview")
async def platform_overview(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Totals across every organisation, for the top of the platform screen."""
    row = (await db.execute(text("""
        SELECT
            (SELECT count(*) FROM tenants)                                    AS organisations,
            (SELECT count(*) FROM users WHERE role = 'employee')              AS employees,
            (SELECT count(*) FROM users WHERE role = 'org_admin')             AS org_admins,
            (SELECT count(*) FROM users WHERE role = 'tenant_admin')          AS tenant_admins,
            (SELECT count(*) FROM devices)                                    AS devices,
            (SELECT count(*) FROM devices WHERE status = 'online')            AS devices_online,
            (SELECT count(*) FROM attendance_logs a
                WHERE a."timestamp" >= date_trunc('day', now()))              AS attendance_today
    """))).mappings().first()
    return dict(row) if row else {}


@router.get("/tenants")
async def list_tenants(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    tenants = (await db.execute(select(Tenant).order_by(func.lower(Tenant.name)))).scalars().all()
    stats = await _stats(db)
    return [_row(t, stats.get(t.id)) for t in tenants]


@router.post("/tenants", status_code=201)
async def create_tenant(
    data: OrganisationCreate,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a working organisation: tenant, first department, office-hours
    settings and a Tenant Admin who can sign in straight away.
    """
    if await _name_taken(db, data.name):
        raise HTTPException(409, f"An organisation called “{data.name}” already exists.")

    # Global, not per-tenant. Sign-in looks accounts up by email alone and takes
    # the first match, so a second account with the same address would make one
    # of the two impossible to sign in to.
    email_taken = (await db.execute(
        select(User.id).where(func.lower(User.email) == data.admin_email)
    )).first()
    if email_taken:
        raise HTTPException(409, f"{data.admin_email} is already used by another account.")

    api_key = new_api_key()
    try:
        tenant = Tenant(name=data.name, api_key=api_key)
        db.add(tenant)
        await db.flush()

        dept = Department(tenant_id=tenant.id, department_name=data.department, is_active=True)
        db.add(dept)
        await db.flush()

        db.add(Settings(tenant_id=tenant.id))

        admin = User(
            tenant_id=tenant.id,
            name=data.admin_name,
            email=data.admin_email,
            password_hash=hash_password(data.admin_password),
            role="tenant_admin",
            dept_id=dept.department_id,
            is_active=True,
        )
        db.add(admin)
        await db.flush()

        await audit.record(
            db, action="organisation.created",
            details={"name": tenant.name, "admin_email": admin.email,
                     "department": dept.department_name},
            **_who(request, current_user, tenant.id),
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Two Super Admins racing on the same name or email: the checks above
        # both passed, the database caught the second insert.
        raise HTTPException(409, "That organisation or admin email was just taken. Try again.")

    await db.refresh(tenant)
    logger.info("Organisation created: %s (id=%s) by user %s", tenant.name, tenant.id, current_user.id)
    stats = await _stats(db, tenant.id)
    return {
        "message": "Organisation created.",
        "tenant": _row(tenant, stats.get(tenant.id)),
        "admin": {"name": data.admin_name, "email": data.admin_email},
        # Shown once. The UI says so, and never asks for it again.
        "api_key": api_key,
    }


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: int,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    stats = await _stats(db, tenant.id)

    admins = (await db.execute(
        select(User.id, User.name, User.email, User.role, User.is_active)
        .where(User.tenant_id == tenant.id, User.role.in_(("tenant_admin", "org_admin")))
        .order_by(User.role.desc(), User.name)
    )).mappings().all()

    settings_row = (await db.execute(
        select(Settings).where(Settings.tenant_id == tenant.id)
    )).scalars().first()

    blockers = await _inventory(db, tenant.id)

    out = _row(tenant, stats.get(tenant.id))
    out.update({
        "admins": [dict(a) for a in admins],
        "settings": {
            "office_start_time": settings_row.office_start_time,
            "office_end_time": settings_row.office_end_time,
            "late_threshold_minutes": settings_row.late_threshold_minutes,
            "working_days": settings_row.working_days,
            "min_working_hours": settings_row.min_working_hours,
        } if settings_row else None,
        "can_delete": not blockers,
        "delete_blockers": blockers,
    })
    return out


@router.patch("/tenants/{tenant_id}")
async def rename_tenant(
    tenant_id: int,
    data: OrganisationRename,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    if data.name == tenant.name:
        return {"message": "Nothing to change.", "tenant": _row(tenant, None)}
    if await _name_taken(db, data.name, except_id=tenant.id):
        raise HTTPException(409, f"An organisation called “{data.name}” already exists.")

    old = tenant.name
    tenant.name = data.name
    await audit.record(
        db, action="organisation.renamed",
        details={"from": old, "to": data.name},
        **_who(request, current_user, tenant.id),
    )
    await db.commit()
    stats = await _stats(db, tenant.id)
    return {"message": "Organisation renamed.", "tenant": _row(tenant, stats.get(tenant.id))}


@router.patch("/tenants/{tenant_id}/reset-api-key")
async def reset_tenant_api_key(
    tenant_id: int,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    tenant.api_key = new_api_key()
    # The key itself stays out of the log — audit._scrub would redact it, but
    # it should never be offered in the first place.
    await audit.record(
        db, action="organisation.api_key_rotated",
        details={"new_key_ends": tenant.api_key[-4:]},
        **_who(request, current_user, tenant.id),
    )
    await db.commit()
    return {
        "message": "New API key issued. The old one stopped working just now — "
                   "update every device and integration that used it.",
        "new_api_key": tenant.api_key,
        "api_key_hint": key_hint(tenant.api_key),
    }


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: int,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    name = tenant.name

    blockers = await _inventory(db, tenant.id)
    if blockers:
        # Recorded, then refused. An attempt to delete a live organisation is
        # exactly the kind of thing its admins would want to know about.
        await audit.record(
            db, action="organisation.delete_refused",
            result="denied", reason="organisation not empty",
            details={"holds": {b["table"]: b["count"] for b in blockers}},
            **_who(request, current_user, tenant.id),
        )
        await db.commit()
        raise HTTPException(409, describe_blockers(blockers))

    existing = set(await _tenant_tables(db))
    try:
        for table in SCAFFOLDING_DELETE_ORDER:
            if table not in existing:
                continue
            if table == "users":
                await db.execute(
                    text("DELETE FROM users WHERE tenant_id = :t AND role = 'tenant_admin'"),
                    {"t": tenant.id},
                )
            else:
                await db.execute(text(f'DELETE FROM "{table}" WHERE tenant_id = :t'), {"t": tenant.id})
        await db.delete(tenant)
        await db.flush()
        await audit.record(
            db, action="organisation.deleted",
            details={"name": name},
            **_who(request, current_user, tenant_id),
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning("Delete of organisation %s blocked by a reference: %s", tenant_id, exc.orig)
        raise HTTPException(
            409,
            "Something still refers to this organisation or its administrator, so it "
            "was left in place and nothing was removed. Check the server log for the "
            "table involved.",
        )

    logger.info("Organisation deleted: %s (id=%s) by user %s", name, tenant_id, current_user.id)
    return {"message": f"“{name}” was deleted."}
