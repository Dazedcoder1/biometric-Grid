"""
Create an organisation (tenant) and its first Org Admin.

Why this exists: tenants can only be created by a Super Admin, and Org Admins
can only be created by a Tenant Admin — who authenticates with that tenant's
API key. On an empty database there is no tenant, so there is no valid API key,
so there is no way in through the UI at all. This script breaks that circle by
writing directly to the database.

    python create_organisation.py "Acme Industries" admin@acme.com

A password is generated unless you pass --password. The tenant API key is
generated and printed once — it is the Tenant Admin credential, so keep it.

Re-running with the same organisation name is safe: it updates the existing
tenant rather than creating a duplicate, and rotates nothing unless you ask.
"""

import argparse
import asyncio
import secrets
import sys

from sqlalchemy import select

from app.core.config import settings as app_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.db.url import describe
from app.models.domain import Department, Settings, Tenant, User

DEFAULT_DEPARTMENT = "General"


def _slug(name: str) -> str:
    """Organisation name to something usable in a default email address."""
    cleaned = "".join(c.lower() if c.isalnum() else "-" for c in name)
    return "-".join(part for part in cleaned.split("-") if part) or "org"


async def run(args) -> int:
    async with AsyncSessionLocal() as db:
        # ── tenant ───────────────────────────────────────────────────────────
        tenant = (
            await db.execute(select(Tenant).where(Tenant.name == args.name))
        ).scalars().first()

        if tenant:
            print(f"  found organisation : {tenant.name} (id={tenant.id})")
            if args.api_key:
                tenant.api_key = args.api_key
                print("  set API key        : old key no longer works")
            elif args.rotate_key:
                tenant.api_key = secrets.token_urlsafe(24)
                print("  rotated API key    : old key no longer works")
            api_key = tenant.api_key
        else:
            api_key = args.api_key or secrets.token_urlsafe(24)
            tenant = Tenant(name=args.name, api_key=api_key)
            db.add(tenant)
            await db.flush()
            print(f"  created organisation : {tenant.name} (id={tenant.id})")

        # ── a department, because users reference one ─────────────────────────
        dept = (
            await db.execute(
                select(Department).where(
                    Department.tenant_id == tenant.id,
                    Department.department_name == args.department,
                )
            )
        ).scalars().first()

        if not dept:
            dept = Department(
                tenant_id=tenant.id, department_name=args.department, is_active=True
            )
            db.add(dept)
            await db.flush()
            print(f"  created department : {dept.department_name} (id={dept.department_id})")
        else:
            print(f"  found department   : {dept.department_name} (id={dept.department_id})")

        # ── office hours: one row per tenant, or attendance has no baseline ───
        existing_settings = (
            await db.execute(select(Settings).where(Settings.tenant_id == tenant.id))
        ).scalars().first()
        if not existing_settings:
            db.add(Settings(tenant_id=tenant.id))
            print("  created settings   : default office hours 09:00-18:00, Mon-Fri")

        # ── the tenant admin ─────────────────────────────────────────────────
        # A real user row, not just an API key. The key still exists for
        # machine-to-machine calls, but a person signing in gets an identity —
        # so the audit log names who acted, and they can enrol a second factor,
        # which an API key can never do.
        tenant_admin_password = args.password or f"Tenant@{secrets.token_hex(4)}"
        tenant_admin_email = args.tenant_admin_email or f"admin@{_slug(args.name)}.local"

        ta = (
            await db.execute(
                select(User).where(
                    User.email == tenant_admin_email, User.tenant_id == tenant.id
                )
            )
        ).scalars().first()

        if ta:
            ta.password_hash = hash_password(tenant_admin_password)
            ta.role = "tenant_admin"
            ta.is_active = True
            print(f"  updated tenant adm : {tenant_admin_email} (password reset)")
        else:
            ta = User(
                tenant_id=tenant.id,
                name=f"{args.name} Administrator",
                email=tenant_admin_email,
                password_hash=hash_password(tenant_admin_password),
                role="tenant_admin",
                dept_id=dept.department_id,
                is_active=True,
            )
            db.add(ta)
            await db.flush()
            print(f"  created tenant adm : {tenant_admin_email}")

        # ── the org admin ────────────────────────────────────────────────────
        password = args.password or f"Admin@{secrets.token_hex(4)}"

        user = (
            await db.execute(
                select(User).where(User.email == args.email, User.tenant_id == tenant.id)
            )
        ).scalars().first()

        if user:
            user.password_hash = hash_password(password)
            user.role = "org_admin"
            user.is_active = True
            user.dept_id = dept.department_id
            print(f"  updated org admin  : {args.email} (password reset)")
        else:
            user = User(
                tenant_id=tenant.id,
                name=args.admin_name or args.email.split("@")[0],
                email=args.email,
                password_hash=hash_password(password),
                role="org_admin",
                dept_id=dept.department_id,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            print(f"  created org admin  : {args.email}")

        # ── an employee ──────────────────────────────────────────────────────
        # Every role needs a working login to test with. Without one, the
        # employee view — which is where most people will actually live — goes
        # unexercised until someone tries it in anger.
        employee_password = args.password or f"Employee@{secrets.token_hex(4)}"
        employee_email = args.employee_email or f"employee@{_slug(args.name)}.local"

        emp = (
            await db.execute(
                select(User).where(
                    User.email == employee_email, User.tenant_id == tenant.id
                )
            )
        ).scalars().first()

        if emp:
            emp.password_hash = hash_password(employee_password)
            emp.role = "employee"
            emp.is_active = True
            print(f"  updated employee   : {employee_email} (password reset)")
        else:
            # employee_code must be unique per tenant. A short random suffix
            # avoids colliding with codes created through the UI.
            emp = User(
                tenant_id=tenant.id,
                name="Test Employee",
                email=employee_email,
                employee_code=f"EMP{secrets.randbelow(9000) + 1000}",
                password_hash=hash_password(employee_password),
                role="employee",
                dept_id=dept.department_id,
                is_active=True,
            )
            db.add(emp)
            await db.flush()
            print(f"  created employee   : {employee_email}")

        await db.commit()

        bar = "=" * 68
        print(f"""
{bar}
ORGANISATION READY
{bar}

  Database          {describe(app_settings.DATABASE_URL)}

  Organisation      {tenant.name}   (tenant id = {tenant.id})

  All three sign in at the same place — /login. There is no role to pick;
  the server works out what each account is from its credentials.

  TENANT ADMIN
    Email           {tenant_admin_email}
    Password        {tenant_admin_password}

  ORG ADMIN
    Email           {args.email}
    Password        {password}

  EMPLOYEE
    Email           {employee_email}
    Code            {emp.employee_code}
    Password        {employee_password}

  API KEY           {api_key}
    For machine-to-machine calls only, in the X-API-Key header. People
    sign in with the email and password above — an API key carries no
    identity, so the audit log could not say who was holding it.

{bar}
From Tenant Admin you can now add departments, employees and further org
admins through the UI. From Org Admin you manage the organisation day to day.
{bar}
""")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an organisation (tenant) and its first Org Admin."
    )
    parser.add_argument("name", help='Organisation name, e.g. "Acme Industries"')
    parser.add_argument("email", help="Email for the first Org Admin")
    parser.add_argument("--password", help="Org Admin password (generated if omitted)")
    parser.add_argument("--admin-name", help="Display name for the Org Admin")
    parser.add_argument(
        "--tenant-admin-email",
        help="Email for the Tenant Admin login. Defaults to admin@<org-slug>.local",
    )
    parser.add_argument(
        "--employee-email",
        help="Email for the test Employee login. Defaults to employee@<org-slug>.local",
    )
    parser.add_argument(
        "--department", default=DEFAULT_DEPARTMENT,
        help=f"Name of the initial department (default: {DEFAULT_DEPARTMENT})",
    )
    parser.add_argument(
        "--api-key",
        help="Use this exact tenant API key instead of a generated one. Handy when "
             "you want to know the key before running. Prefer the generated key "
             "for anything beyond local development.",
    )
    parser.add_argument(
        "--rotate-key", action="store_true",
        help="If the organisation already exists, issue it a new API key",
    )
    args = parser.parse_args()

    if "@" not in args.email:
        print(f"'{args.email}' does not look like an email address.")
        return 1

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
