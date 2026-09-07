"""
Create test accounts for all three roles, plus sample tasks.

Idempotent: re-running updates the existing rows rather than duplicating, so
it's safe to run whenever you want passwords reset to known values.

    python seed_test_accounts.py

These are DEVELOPMENT credentials with deliberately obvious passwords. Do not
run this against a production database.
"""

import asyncio
import secrets
import sys
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.domain import (
    Department, Settings, Task, TaskPriority, TaskSource, TaskStatus, Tenant, User,
)

# ─── Test credentials ─────────────────────────────────────────────────────────
TENANT_NAME = "Test Organisation"
TENANT_API_KEY = "test-tenant-key-0000000000000000"

ORG_ADMIN_EMAIL = "orgadmin@test.local"
ORG_ADMIN_PASSWORD = "OrgAdmin@123"

EMPLOYEE_PASSWORD = "Employee@123"

# Five employees, all sharing one password so testing is quick.
# github_username is what lets task assignment mirror onto a GitHub issue —
# left blank here since these are fictional people; set real logins from
# Tenant Admin -> GitHub Repos -> GitHub usernames.
EMPLOYEES = [
    {"code": "EMP001", "email": "employee@test.local",  "name": "Test Employee"},
    {"code": "EMP002", "email": "employee2@test.local", "name": "Priya Raman"},
    {"code": "EMP003", "email": "employee3@test.local", "name": "Daniel Okafor"},
    {"code": "EMP004", "email": "employee4@test.local", "name": "Mei Lin Chen"},
    {"code": "EMP005", "email": "employee5@test.local", "name": "Jonas Weber"},
]

# Kept so anything referencing the original single employee still resolves.
EMPLOYEE_EMAIL = EMPLOYEES[0]["email"]
EMPLOYEE_CODE = EMPLOYEES[0]["code"]

DEPARTMENT_NAME = "Engineering"


async def upsert_tenant(db) -> Tenant:
    tenant = (
        await db.execute(select(Tenant).where(Tenant.name == TENANT_NAME))
    ).scalars().first()

    if tenant:
        tenant.api_key = TENANT_API_KEY
        print(f"  updated tenant  : {tenant.name} (id={tenant.id})")
    else:
        tenant = Tenant(name=TENANT_NAME, api_key=TENANT_API_KEY)
        db.add(tenant)
        await db.flush()
        print(f"  created tenant  : {tenant.name} (id={tenant.id})")
    return tenant


async def upsert_department(db, tenant: Tenant) -> Department:
    dept = (
        await db.execute(
            select(Department).where(
                Department.tenant_id == tenant.id,
                Department.department_name == DEPARTMENT_NAME,
            )
        )
    ).scalars().first()

    if not dept:
        dept = Department(
            tenant_id=tenant.id, department_name=DEPARTMENT_NAME, is_active=True
        )
        db.add(dept)
        await db.flush()
        print(f"  created dept    : {dept.department_name} (id={dept.department_id})")
    else:
        print(f"  found dept      : {dept.department_name} (id={dept.department_id})")
    return dept


async def upsert_user(db, tenant, dept, *, email, password, name, role, code=None) -> User:
    user = (
        await db.execute(
            select(User).where(User.email == email, User.tenant_id == tenant.id)
        )
    ).scalars().first()

    if user:
        user.password_hash = hash_password(password)
        user.role = role
        user.is_active = True
        user.dept_id = dept.department_id
        print(f"  updated user    : {email} ({role})")
    else:
        user = User(
            tenant_id=tenant.id,
            name=name,
            email=email,
            employee_code=code,
            password_hash=hash_password(password),
            role=role,
            dept_id=dept.department_id,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        print(f"  created user    : {email} ({role})")
    return user


async def seed_sample_tasks(db, tenant, dept, org_admin, employees):
    """
    Manual tasks so the board isn't empty before GitHub is connected.

    Spread across all five employees and every status, so filtering, the stats
    cards and the per-employee 'My Tasks' view all have something to show.
    """
    existing = (
        await db.execute(
            select(Task).where(
                Task.tenant_id == tenant.id, Task.source == TaskSource.MANUAL.value
            )
        )
    ).scalars().all()

    if existing:
        print(f"  tasks           : {len(existing)} manual task(s) already present, skipping")
        return

    e = [u.id for u in employees]
    samples = [
        ("Set up staging environment",    TaskStatus.IN_PROGRESS, TaskPriority.HIGH,   e[0],  3),
        ("Review Q3 attendance report",   TaskStatus.TODO,        TaskPriority.MEDIUM, e[0],  7),
        ("Rotate device API keys",        TaskStatus.TODO,        TaskPriority.URGENT, None,  1),
        ("Write onboarding docs",         TaskStatus.IN_REVIEW,   TaskPriority.LOW,    e[1], 14),
        ("Fix timezone bug in reports",   TaskStatus.DONE,        TaskPriority.HIGH,   e[1], -2),
        ("Migrate fingerprint templates", TaskStatus.IN_PROGRESS, TaskPriority.URGENT, e[2],  2),
        ("Audit device firmware versions",TaskStatus.TODO,        TaskPriority.MEDIUM, e[2],  9),
        ("Add leave-balance unit tests",  TaskStatus.IN_REVIEW,   TaskPriority.MEDIUM, e[3],  5),
        ("Document the MQTT topic map",   TaskStatus.TODO,        TaskPriority.LOW,    e[3], 21),
        ("Investigate duplicate punches", TaskStatus.IN_PROGRESS, TaskPriority.HIGH,   e[4],  4),
        ("Clean up stale refresh tokens", TaskStatus.DONE,        TaskPriority.LOW,    e[4], -5),
        ("Plan Q4 device rollout",        TaskStatus.TODO,        TaskPriority.MEDIUM, None, 30),
    ]

    for title, status, priority, assignee, due_in_days in samples:
        db.add(Task(
            tenant_id=tenant.id,
            title=title,
            description=f"Sample task seeded for testing: {title.lower()}.",
            source=TaskSource.MANUAL.value,
            status=status.value,
            priority=priority.value,
            dept_id=dept.department_id,
            assigned_to=assignee,
            created_by=org_admin.id,
            due_date=datetime.utcnow() + timedelta(days=due_in_days),
            completed_at=datetime.utcnow() if status == TaskStatus.DONE else None,
        ))
    print(f"  created tasks   : {len(samples)} sample tasks")


async def ensure_settings(db, tenant):
    row = (
        await db.execute(select(Settings).where(Settings.tenant_id == tenant.id))
    ).scalars().first()
    if not row:
        db.add(Settings(tenant_id=tenant.id))
        print("  created settings: default office hours")


async def main():
    print("\nSeeding test accounts…\n")
    async with AsyncSessionLocal() as db:
        tenant = await upsert_tenant(db)
        dept = await upsert_department(db, tenant)

        org_admin = await upsert_user(
            db, tenant, dept,
            email=ORG_ADMIN_EMAIL, password=ORG_ADMIN_PASSWORD,
            name="Test Org Admin", role="org_admin",
        )
        employees = []
        for spec in EMPLOYEES:
            employees.append(await upsert_user(
                db, tenant, dept,
                email=spec["email"], password=EMPLOYEE_PASSWORD,
                name=spec["name"], role="employee", code=spec["code"],
            ))

        await ensure_settings(db, tenant)
        await seed_sample_tasks(db, tenant, dept, org_admin, employees)
        await db.commit()

    print(f"""
{'=' * 64}
TEST CREDENTIALS
{'=' * 64}

  TENANT ADMIN        http://localhost:5173/login/tenant
    API Key           {TENANT_API_KEY}
    (no password — this role authenticates by key)

  ORG ADMIN           http://localhost:5173/login/org
    Email             {ORG_ADMIN_EMAIL}
    Password          {ORG_ADMIN_PASSWORD}

  EMPLOYEES ({len(EMPLOYEES)})       http://localhost:5173/login/employee
    Password          {EMPLOYEE_PASSWORD}   (same for all five)
    Sign in with either the email or the employee code.

{chr(10).join(f"      {s['code']}  {s['email']:<24} {s['name']}" for s in EMPLOYEES)}

{'=' * 64}
Development credentials only — never run this against production.
{'=' * 64}
""")


if __name__ == "__main__":
    if "--production-i-am-sure" not in sys.argv:
        # Cheap guard against pasting this into the wrong shell.
        from app.core.config import settings
        url = settings.DATABASE_URL
        local_markers = ("localhost", "127.0.0.1", "172.17.0.1", "@pg", "sqlite")
        if not any(h in url for h in local_markers):
            print(f"\nRefusing to seed: DATABASE_URL doesn't look local.\n  {url}\n"
                  "Re-run with --production-i-am-sure if you really mean it.\n")
            sys.exit(1)

    asyncio.run(main())
