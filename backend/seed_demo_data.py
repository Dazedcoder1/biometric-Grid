"""
Seed a complete, exercisable dataset — every role, every screen.

`seed_test_accounts.py` creates accounts. This creates a working organisation:
history to look at, requests to approve, devices to command, credentials to
reveal. The difference matters, because most of this application's screens are
views over data that has accumulated, and an empty table and a broken endpoint
look identical from the browser. Several of the bugs found recently were only
visible once there was something to render.

    python seed_demo_data.py            # create or update
    python seed_demo_data.py --reset    # delete the demo tenants first
    python seed_demo_data.py --force    # run against a non-empty database

What you get:

  * TWO organisations. One is not enough: it cannot exercise the Super Admin
    organisation chooser, and it cannot catch a query that forgets to filter
    by tenant — the commonest and least visible bug in a multi-tenant system.
    The second organisation exists mainly so that leaking into it is possible.
  * All four roles, each with a password, including a platform Super Admin.
  * Two departments per organisation, so department scoping is observable.
  * 60 days of attendance with late arrivals, short days, absences and
    weekends — enough for the compliance percentages to be interesting rather
    than 0% or 100%.
  * Leave requests in every state a screen can render.
  * Holidays before and after today, so "upcoming" is meaningfully different
    from "all".
  * Devices, one online and one stale, plus queued commands.
  * Notifications, so the activity feed and the bell have content.
  * A credential vault with real encrypted secrets, shares at several
    permission levels, systems and dependencies.

Passwords are deliberately obvious. This is a development tool.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.core.permissions import PermissionSet
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.db.url import describe
from app.core.config import settings as app_settings
from app.models.credentials import (
    Credential,
    CredentialDependency,
    Rack,
    RotationPolicy,
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
    Holiday,
    Leave,
    Notification,
    Settings,
    Task,
    Tenant,
    User,
)
from app.services import share_service, vault_service

# Deterministic: two runs produce the same history, so a screenshot from
# yesterday still matches what you see today and "did my change break this?"
# has an answer.
random.seed(20260929)

PASSWORD = "Demo@1234"          # every seeded account
SUPER_ADMIN_EMAIL = "super@demo.local"

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
HISTORY_DAYS = 60


# ─────────────────────────────────────────────────────────────────────────────
# Shape of the demo data
# ─────────────────────────────────────────────────────────────────────────────

ORGS = [
    {
        "name": "Northwind Logistics",
        "api_key": "demo-northwind-key-000000000001",
        "slug": "northwind",
        "departments": [
            {
                "name": "Operations",
                "org_admin": ("Ops Admin", "ops.admin@northwind.local"),
                "employees": [
                    ("EMP-NW-001", "Aarti Deshpande", "aarti@northwind.local", 1),
                    ("EMP-NW-002", "Tomás Herrera", "tomas@northwind.local", 2),
                    ("EMP-NW-003", "Grace Mwangi", "grace@northwind.local", 3),
                    ("EMP-NW-004", "Liam O'Connell", "liam@northwind.local", 4),
                ],
            },
            {
                "name": "Engineering",
                "org_admin": ("Eng Admin", "eng.admin@northwind.local"),
                "employees": [
                    ("EMP-NW-101", "Sofia Rossi", "sofia@northwind.local", 11),
                    ("EMP-NW-102", "Kwame Asante", "kwame@northwind.local", 12),
                    ("EMP-NW-103", "Yuki Tanaka", "yuki@northwind.local", 13),
                ],
            },
        ],
    },
    {
        # Exists so that cross-tenant leakage is possible, and therefore
        # testable. Smaller on purpose — you should never see these names while
        # signed in to Northwind.
        "name": "Harbour Freight Co",
        "api_key": "demo-harbour-key-0000000000002",
        "slug": "harbour",
        "departments": [
            {
                "name": "Warehouse",
                "org_admin": ("Warehouse Admin", "wh.admin@harbour.local"),
                "employees": [
                    ("EMP-HF-001", "Ingrid Halvorsen", "ingrid@harbour.local", 21),
                    ("EMP-HF-002", "Rafael Duarte", "rafael@harbour.local", 22),
                ],
            },
        ],
    },
]


class Ctx:
    """
    The minimum `vault_service` and `share_service` need.

    They take a SecurityContext because they run inside a request and audit
    every action. Here there is no request, so this stands in — with
    grants_all, because a seeder is not the place to model authorisation.
    """

    def __init__(self, user: User):
        self.user = user
        self.permissions = PermissionSet(grants_all=True)
        self.session_jti = None
        self.source_ip = "127.0.0.1"
        self.user_agent = "seed_demo_data.py"

    def audit_kwargs(self) -> dict:
        return {
            "tenant_id": self.user.tenant_id,
            "actor_id": self.user.id,
            "actor_role": self.user.role,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "session_jti": self.session_jti,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def log(section: str, message: str) -> None:
    print(f"  {section:<14} {message}")


async def upsert_user(db, *, tenant_id, dept_id, name, email, role, code=None,
                      finger_id=None) -> User:
    user = (await db.execute(
        select(User).where(User.email == email)
    )).scalars().first()

    if user:
        user.tenant_id = tenant_id
        user.dept_id = dept_id
        user.name = name
        user.role = role
        user.employee_code = code
        user.finger_id = finger_id
        user.password_hash = hash_password(PASSWORD)
        user.is_active = True
    else:
        user = User(
            tenant_id=tenant_id, dept_id=dept_id, name=name, email=email,
            employee_code=code, finger_id=finger_id, role=role,
            password_hash=hash_password(PASSWORD), is_active=True,
        )
        db.add(user)
    await db.flush()
    return user


def working_day(d) -> bool:
    return d.weekday() < 5


def naive(dt: datetime) -> datetime:
    """
    Drop the timezone for columns declared as plain DateTime.

    The schema is inconsistent about this and it is not this script's place to
    fix it: `created_at` and friends are DateTime(timezone=True), while
    Leave.start_date, Leave.end_date, Holiday.holiday_date and Task.due_date
    are naive. Handing an aware datetime to a `timestamp without time zone`
    column makes asyncpg fail with "can't subtract offset-naive and
    offset-aware datetimes", which names the symptom and not the column.

    These are all whole-day fields — a leave starts on a date, not at an
    instant — so discarding the offset loses nothing real. Converting to UTC
    first means the date is the UTC date regardless of where this is run.
    """
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# Builders
# ─────────────────────────────────────────────────────────────────────────────

async def build_attendance(db, tenant, employees, device_id: str) -> int:
    """
    Sixty days of punches.

    The variety is the point. A dataset where everyone arrives at 09:00 and
    leaves at 18:00 makes every compliance figure 100% and every late-arrival
    filter empty, so the screens look right whether or not they work. Each
    person here gets a different reliability, and one is a habitual late
    arriver, so "late today" and "below minimum hours" both have rows.
    """
    existing = (await db.execute(
        select(func.count(AttendanceLog.id)).where(AttendanceLog.tenant_id == tenant.id)
    )).scalar_one()
    if existing:
        log("attendance", f"{existing} punches already present, skipping")
        return 0

    # (probability present, minutes late on average, hours worked)
    profiles = [
        (0.97, 2, 9.2),    # reliable
        (0.90, 25, 8.4),   # habitually late, slightly short days
        (0.99, 0, 9.6),    # early and long
        (0.82, 8, 7.6),    # frequently absent, short days
        (0.94, 5, 9.0),
        (0.88, 15, 8.8),
        (0.96, 3, 9.1),
    ]

    rows = 0
    for index, emp in enumerate(employees):
        present_p, late_avg, hours = profiles[index % len(profiles)]
        for back in range(HISTORY_DAYS):
            day = TODAY - timedelta(days=back)
            if not working_day(day):
                continue
            if random.random() > present_p:
                continue  # absent — no rows at all, which is how absence reads

            late = max(0, int(random.gauss(late_avg, 12)))
            check_in = datetime(day.year, day.month, day.day, 9, 0,
                                tzinfo=timezone.utc) + timedelta(minutes=late)
            worked = max(4.0, random.gauss(hours, 0.7))
            check_out = check_in + timedelta(hours=worked)

            db.add(AttendanceLog(
                tenant_id=tenant.id, device_id=device_id, user_id=emp.id,
                finger_id=emp.finger_id or 1, record_type="IN", timestamp=check_in,
            ))
            db.add(AttendanceLog(
                tenant_id=tenant.id, device_id=device_id, user_id=emp.id,
                finger_id=emp.finger_id or 1, record_type="OUT", timestamp=check_out,
            ))
            rows += 2
    log("attendance", f"{rows} punches across {HISTORY_DAYS} days")
    return rows


async def build_leaves(db, tenant, employees, org_admin) -> int:
    """One leave in every state a screen can render, so no branch is untested."""
    if (await db.execute(
        select(func.count(Leave.leave_id)).where(Leave.tenant_id == tenant.id)
    )).scalar_one():
        log("leaves", "already present, skipping")
        return 0

    specs = [
        # (employee index, type, starts in N days, length, status)
        (0, "casual", 3, 2, "pending"),
        (1, "sick", -2, 1, "pending"),
        (2, "earned", 10, 5, "approved_by_dept"),
        (0, "sick", -20, 2, "approved"),
        (3, "casual", -35, 1, "rejected"),
        (1, "earned", 21, 3, "pending"),
        (2, "casual", -8, 1, "approved"),
        (3, "sick", -1, 1, "cancelled"),
    ]
    for emp_i, kind, offset, length, status in specs:
        emp = employees[emp_i % len(employees)]
        start = NOW + timedelta(days=offset)
        leave = Leave(
            tenant_id=tenant.id,
            employee_id=emp.id,
            leave_type=kind,
            start_date=naive(start),
            end_date=naive(start + timedelta(days=length - 1)),
            reason=f"Seeded {kind} leave for {emp.name}",
            status=status,
            created_at=start - timedelta(days=4),
        )
        if status in ("approved_by_dept", "approved"):
            leave.dept_approved_at = start - timedelta(days=3)
            leave.dept_approved_by = org_admin.id
        if status == "approved":
            leave.approved_at = start - timedelta(days=2)
            leave.approved_by = org_admin.id
        if status == "rejected":
            leave.rejected_at = start - timedelta(days=3)
            leave.rejection_reason = "Two people already away that week."
        db.add(leave)
    log("leaves", f"{len(specs)} requests across every status")
    return len(specs)


async def build_holidays(db, tenant) -> int:
    if (await db.execute(
        select(func.count(Holiday.holiday_id)).where(Holiday.tenant_id == tenant.id)
    )).scalar_one():
        log("holidays", "already present, skipping")
        return 0

    # Both sides of today, so "upcoming" differs from "all" — a list that only
    # ever grows forwards hides an ordering bug.
    specs = [
        ("New Year's Day", -240), ("Spring Bank Holiday", -70),
        ("Founders' Day", -12), ("Summer Shutdown", 18),
        ("Autumn Festival", 47), ("Year-End Close", 96),
    ]
    for name, offset in specs:
        db.add(Holiday(
            tenant_id=tenant.id, name=name,
            holiday_date=naive(NOW + timedelta(days=offset)),
            description=f"{name} — seeded demo holiday.",
        ))
    log("holidays", f"{len(specs)} ({sum(1 for _, o in specs if o > 0)} upcoming)")
    return len(specs)


async def build_devices(db, tenant, slug: str) -> list[str]:
    ids = [f"{slug}-lobby-01", f"{slug}-warehouse-02"]
    for i, device_id in enumerate(ids):
        existing = (await db.execute(
            select(Device).where(Device.tenant_id == tenant.id,
                                 Device.device_id == device_id)
        )).scalars().first()
        if existing:
            continue
        db.add(Device(
            tenant_id=tenant.id, device_id=device_id,
            secret_key=f"demo-secret-{slug}-{i}",
            # One online, one long-silent. The Devices page marks a device
            # "stale" when it claims to be online but has not been seen — that
            # branch needs a device in exactly that state to be visible.
            status="online" if i == 0 else "offline",
            last_seen=NOW - timedelta(minutes=2 if i == 0 else 4000),
        ))
    await db.flush()
    log("devices", f"{len(ids)} ({ids[0]} online, {ids[1]} offline)")
    return ids


async def build_commands(db, tenant, device_id: str, employees) -> None:
    if (await db.execute(
        select(func.count(Command.id)).where(Command.tenant_id == tenant.id)
    )).scalar_one():
        return
    for emp, cmd in [(employees[0], "ENROLL"), (employees[1], "DELETE")]:
        db.add(Command(tenant_id=tenant.id, device_id=device_id,
                       command=cmd, target_id=emp.id))
    log("commands", "2 queued")


async def build_notifications(db, tenant, org_admin, employees) -> None:
    """Content for the activity feed and the notification bell."""
    if (await db.execute(
        select(func.count(Notification.notification_id))
        .where(Notification.tenant_id == tenant.id)
    )).scalar_one():
        log("notifications", "already present, skipping")
        return

    specs = [
        ("leave_requested", "Leave requested", "{who} requested casual leave", 0, False),
        ("leave_approved", "Leave approved", "Your sick leave was approved", 0, True),
        ("attendance_marked", "Checked in", "{who} checked in at 09:04", 1, True),
        ("late_arrival", "Late arrival", "{who} arrived 27 minutes late", 1, False),
        ("employee_added", "Employee added", "{who} joined the department", 2, False),
        ("fingerprint_enrolled", "Fingerprint enrolled",
         "{who} enrolled on the lobby reader", 2, True),
        ("leave_rejected", "Leave rejected",
         "Your casual leave was rejected: two people already away", 3, False),
    ]
    for i, (event, title, message, emp_i, read) in enumerate(specs):
        emp = employees[emp_i % len(employees)]
        db.add(Notification(
            tenant_id=tenant.id,
            actor_id=org_admin.id,
            actor_name=org_admin.name,
            recipient_id=emp.id,
            event_type=event,
            entity_type="user",
            entity_id=emp.id,
            entity_name=emp.name,
            title=title,
            message=message.format(who=emp.name),
            is_read=read,
            created_at=NOW - timedelta(hours=i * 7 + 1),
        ))
    log("notifications", f"{len(specs)} events")


async def build_vault(db, tenant, org_admin, employees) -> None:
    """
    Credentials, shares, systems and dependencies.

    Written through vault_service rather than as raw rows, so the secrets are
    genuinely encrypted, the versions and audit entries exist, and Reveal
    actually returns something. Inserting Credential rows directly would give a
    vault that lists correctly and fails the moment you open anything.
    """
    if (await db.execute(
        select(func.count(Credential.id)).where(Credential.tenant_id == tenant.id)
    )).scalar_one():
        log("vault", "credentials already present, skipping")
        return

    ctx = Ctx(org_admin)
    vaults = await vault_service.ensure_vaults(db, org_admin)
    racks = (await db.execute(
        select(Rack).where(Rack.vault_id == vaults["personal"].id).order_by(Rack.sort_order)
    )).scalars().all()
    by_name = {r.name: r for r in racks}

    specs = [
        ("General",   "Payroll portal",    "password",    "payroll-admin",
         "https://payroll.example.com", "Finance signs off before any change.", True),
        ("GitHub",    "Deploy bot token",  "token",       "deploy-bot",
         "https://github.com/northwind", None, False),
        ("Databases", "Primary Postgres",  "password",    "app_rw",
         None, "Read-write role used by the API.", False),
        ("Databases", "Analytics replica", "password",    "analytics_ro",
         None, None, False),
        ("Google",    "Workspace admin",   "password",    "admin@northwind",
         "https://admin.google.com", "Recovery codes in the safe.", True),
        ("General",   "Reader firmware signing key", "ssh_key", None,
         None, "Passphrase held by two people.", False),
    ]

    created = []
    for rack_name, name, kind, username, url, notes, has_2fa in specs:
        rack = by_name.get(rack_name) or racks[0]
        cred = await vault_service.create_credential(
            db, ctx=ctx, rack_id=rack.id, name=name,
            # Distinct per credential so a bug that mixes ciphertext between
            # rows shows up as the wrong secret rather than as a plausible one.
            secret=f"s3cr3t-{name.lower().replace(' ', '-')}-{random.randint(1000, 9999)}",
            kind=kind, username=username, url=url, notes=notes, has_2fa=has_2fa,
        )
        created.append(cred)

    # Expiry: one overdue, one close, one comfortable, the rest unset. The row
    # chips key off this, and "no expiry" must stay common enough that the
    # warning colours still mean something.
    created[0].expires_at = NOW - timedelta(days=5)
    created[1].expires_at = NOW + timedelta(days=4)
    created[2].expires_at = NOW + timedelta(days=80)
    created[3].last_accessed_at = NOW - timedelta(hours=6)
    created[4].last_accessed_at = NOW - timedelta(days=40)

    # A team, so the share tree has both a user branch and a team branch.
    team = Team(tenant_id=tenant.id, name="On-call", created_by=org_admin.id)
    db.add(team)
    await db.flush()
    for member in employees[:2]:
        db.add(TeamMember(team_id=team.id, user_id=member.id, added_by=org_admin.id))
    await db.flush()

    # Indexed modulo the roster: the second organisation is deliberately
    # smaller, and a seeder that only works for the big one is a seeder that
    # stops working the first time somebody edits ORGS.
    def emp(i: int) -> User:
        return employees[i % len(employees)]

    shares = 0
    await share_service.grant(db, ctx=ctx, credential=created[0],
                              permission="reveal", grantee_user_id=emp(0).id)
    await share_service.grant(db, ctx=ctx, credential=created[1],
                              permission="view", grantee_user_id=emp(1).id)
    await share_service.grant(db, ctx=ctx, credential=created[2],
                              permission="edit", grantee_team_id=team.id)
    shares += 3
    # One that expires soon, so the "expires" column is not always blank. Only
    # when there is a third person to give it to — otherwise it would duplicate
    # an existing share and the tree would show the same name twice.
    if len(employees) > 2:
        await share_service.grant(db, ctx=ctx, credential=created[4],
                                  permission="reveal", grantee_user_id=emp(2).id,
                                  expires_at=NOW + timedelta(days=2))
        shares += 1

    systems = []
    for name, kind, env in [
        ("payments-api", "service", "production"),
        ("warehouse-scanner", "service", "production"),
        ("staging-api", "service", "staging"),
        ("nightly-etl", "job", "production"),
    ]:
        system = System(tenant_id=tenant.id, name=name, kind=kind, environment=env)
        db.add(system)
        systems.append(system)
    await db.flush()

    # Deliberately leaves two credentials unmapped: the dependency map's
    # "unmapped" warning is one of the few things on that page that can be
    # wrong in a way nobody notices, and it needs a non-zero count to prove it.
    for cred, system in [
        (created[2], systems[0]), (created[2], systems[3]),
        (created[1], systems[2]), (created[0], systems[0]),
        (created[4], systems[1]),
    ]:
        db.add(CredentialDependency(credential_id=cred.id, system_id=system.id,
                                    created_by=org_admin.id))

    db.add(RotationPolicy(tenant_id=tenant.id, credential_id=created[0].id,
                          interval_days=90, warn_days_before=14, enabled=True))
    db.add(RotationPolicy(tenant_id=tenant.id, credential_id=created[2].id,
                          interval_days=180, warn_days_before=30, enabled=True))

    log("vault", f"{len(created)} credentials, {shares} shares, "
                 f"{len(systems)} systems, 2 unmapped")


# ─────────────────────────────────────────────────────────────────────────────
# Reset
# ─────────────────────────────────────────────────────────────────────────────

async def reset(db) -> None:
    """
    Remove the demo organisations and everything hanging off them.

    Ordered child-first. Several foreign keys are RESTRICT rather than CASCADE
    — deliberately, so that a user or rack holding credentials cannot be
    deleted out from under them — which means the order here is load-bearing
    and not a stylistic choice.
    """
    names = [o["name"] for o in ORGS]
    tenants = (await db.execute(select(Tenant).where(Tenant.name.in_(names)))).scalars().all()
    if not tenants:
        log("reset", "no demo organisations found")
        return
    ids = [t.id for t in tenants]

    vault_ids = [v.id for v in (await db.execute(
        select(Vault).where(Vault.tenant_id.in_(ids)))).scalars().all()]
    cred_ids = [c.id for c in (await db.execute(
        select(Credential).where(Credential.tenant_id.in_(ids)))).scalars().all()]
    team_ids = [t.id for t in (await db.execute(
        select(Team).where(Team.tenant_id.in_(ids)))).scalars().all()]

    from app.models.credentials import (
        CredentialVersion, EncryptedPayload, OwnershipHistory, Share,
    )

    if cred_ids:
        version_ids = [v.id for v in (await db.execute(
            select(CredentialVersion)
            .where(CredentialVersion.credential_id.in_(cred_ids)))).scalars().all()]
        payload_ids = [v.payload_id for v in (await db.execute(
            select(CredentialVersion)
            .where(CredentialVersion.credential_id.in_(cred_ids)))).scalars().all()]

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
                             .where(EncryptedPayload.id.in_([p for p in payload_ids if p])))
        await db.execute(delete(Credential).where(Credential.id.in_(cred_ids)))

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
    await db.execute(delete(Task).where(Task.tenant_id.in_(ids)))
    await db.execute(delete(Settings).where(Settings.tenant_id.in_(ids)))
    await db.execute(delete(User).where(User.tenant_id.in_(ids)))
    await db.execute(delete(Department).where(Department.tenant_id.in_(ids)))
    await db.execute(delete(Tenant).where(Tenant.id.in_(ids)))
    await db.commit()
    log("reset", f"removed {len(tenants)} demo organisation(s)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def guard_against_production(db, force: bool) -> bool:
    """
    Refuse to run against a database that looks like somebody's real data.

    This script writes 60 days of invented attendance and resets passwords to a
    published value. The check is crude — unknown organisations present — but
    the failure it prevents is not.
    """
    if force:
        return True
    known = {o["name"] for o in ORGS} | {"Test Organisation"}
    others = [t.name for t in (await db.execute(select(Tenant))).scalars().all()
              if t.name not in known]
    if others:
        print(
            "\nRefusing to run: this database already contains organisations "
            "this script did not create —\n  "
            + "\n  ".join(others[:10])
            + "\n\nIt would reset passwords to a published value and add invented "
              "attendance.\nIf this is a development database, re-run with --force.\n"
        )
        return False
    return True


async def seed_org(db, spec: dict) -> dict:
    print(f"\n{spec['name']}")

    tenant = (await db.execute(
        select(Tenant).where(Tenant.name == spec["name"]))).scalars().first()
    if tenant:
        tenant.api_key = spec["api_key"]
    else:
        tenant = Tenant(name=spec["name"], api_key=spec["api_key"])
        db.add(tenant)
        await db.flush()
    log("tenant", f"id={tenant.id}")

    row = (await db.execute(
        select(Settings).where(Settings.tenant_id == tenant.id))).scalars().first()
    if not row:
        db.add(Settings(tenant_id=tenant.id, min_working_hours=9.0))
        log("settings", "09:00-18:00, 15 min grace, 9h minimum")

    tenant_admin = await upsert_user(
        db, tenant_id=tenant.id, dept_id=None,
        name=f"{spec['name']} Administrator",
        email=f"admin@{spec['slug']}.local", role="tenant_admin",
    )

    accounts = {"tenant_admin": tenant_admin.email, "org_admins": [], "employees": []}
    all_employees: list[User] = []
    first_org_admin = None

    for dept_spec in spec["departments"]:
        dept = (await db.execute(select(Department).where(
            Department.tenant_id == tenant.id,
            Department.department_name == dept_spec["name"],
        ))).scalars().first()
        if not dept:
            dept = Department(tenant_id=tenant.id,
                              department_name=dept_spec["name"], is_active=True)
            db.add(dept)
            await db.flush()

        admin_name, admin_email = dept_spec["org_admin"]
        org_admin = await upsert_user(
            db, tenant_id=tenant.id, dept_id=dept.department_id,
            name=admin_name, email=admin_email, role="org_admin",
        )
        first_org_admin = first_org_admin or org_admin
        accounts["org_admins"].append((dept_spec["name"], admin_email))

        for code, name, email, finger in dept_spec["employees"]:
            emp = await upsert_user(
                db, tenant_id=tenant.id, dept_id=dept.department_id,
                name=name, email=email, role="employee", code=code, finger_id=finger,
            )
            all_employees.append(emp)
            accounts["employees"].append((code, email, dept_spec["name"]))

        log("department", f"{dept_spec['name']}: 1 admin, "
                          f"{len(dept_spec['employees'])} employees")

    devices = await build_devices(db, tenant, spec["slug"])
    await build_attendance(db, tenant, all_employees, devices[0])
    await build_leaves(db, tenant, all_employees, first_org_admin)
    await build_holidays(db, tenant)
    await build_commands(db, tenant, devices[0], all_employees)
    await build_notifications(db, tenant, first_org_admin, all_employees)
    await build_vault(db, tenant, first_org_admin, all_employees)

    await db.commit()
    return accounts


async def main(args) -> int:
    print(f"\nDatabase: {describe(app_settings.DATABASE_URL)}")

    async with AsyncSessionLocal() as db:
        if args.reset:
            await reset(db)
            if args.reset_only:
                return 0

        if not await guard_against_production(db, args.force):
            return 1

        super_admin = (await db.execute(
            select(User).where(User.email == SUPER_ADMIN_EMAIL))).scalars().first()
        if super_admin:
            super_admin.password_hash = hash_password(PASSWORD)
            super_admin.is_active = True
        else:
            # tenant_id stays NULL: a Super Admin belongs to the platform. This
            # is exactly the account that needs the organisation chooser.
            db.add(User(
                tenant_id=None, dept_id=None, name="Platform Super Admin",
                email=SUPER_ADMIN_EMAIL, role="super_admin",
                password_hash=hash_password(PASSWORD), is_active=True,
            ))
        await db.commit()

        results = [await seed_org(db, spec) for spec in ORGS]

    bar = "=" * 74
    print(f"\n{bar}\nSIGN IN AT  /login   —  every account uses the password below\n{bar}")
    print(f"\n  PASSWORD           {PASSWORD}\n")
    print(f"  SUPER ADMIN        {SUPER_ADMIN_EMAIL}")
    print("                     No organisation of its own — you will be asked to")
    print("                     pick one, and can switch from the sidebar.\n")

    for spec, accounts in zip(ORGS, results):
        print(f"  {spec['name'].upper()}")
        print(f"    Tenant Admin     {accounts['tenant_admin']}")
        for dept, email in accounts["org_admins"]:
            print(f"    Org Admin        {email:<34} ({dept})")
        for code, email, dept in accounts["employees"]:
            print(f"    Employee         {email:<34} {code}  ({dept})")
        print(f"    API key          {spec['api_key']}")
        print()

    print(bar)
    print("Sign in as an Org Admin to see attendance, leave approvals and the")
    print("activity feed with data. The vault belongs to the first Org Admin of")
    print("each organisation; employees see what was shared with them.")
    print(bar + "\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--reset", action="store_true",
                        help="delete the demo organisations before seeding")
    parser.add_argument("--reset-only", action="store_true",
                        help="delete and stop, without reseeding")
    parser.add_argument("--force", action="store_true",
                        help="run even though unrecognised organisations exist")
    parsed = parser.parse_args()
    if parsed.reset_only:
        parsed.reset = True
    sys.exit(asyncio.run(main(parsed)))
