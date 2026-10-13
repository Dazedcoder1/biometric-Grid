"""
Activity timelines, the audit log viewer, CSV export and chain verification.

Everything here is read-only. The audit log has no write endpoint by design —
entries are written by the code performing the action, inside the same
transaction, and the application's database role holds no UPDATE or DELETE on
the table. An HTTP route that could append to it would be a way to forge
history.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import (
    SecurityContext,
    require_permission,
)
from app.core import audit
from app.db.session import get_db
from app.models.credentials import Credential, System
from app.models.domain import Leave, Task, Tenant, User
from app.models.security import AuditLog
from app.services import vault_service as svc

router = APIRouter()

#: Actions that belong on a credential's timeline. Everything else in the audit
#: log — logins, MFA, role changes — is noise at this zoom level.
CREDENTIAL_ACTIONS = (
    "credential.created", "credential.viewed", "credential.revealed",
    # An administrator looking at it from the People page belongs on the
    # owner's timeline more than anything else here.
    "credential.revealed_by_admin", "credential.changed_by_admin",
    "credential.copied", "credential.updated", "credential.rotated",
    "credential.deleted", "credential.tamper_detected",
    "share.granted", "share.revoked", "share.expired",
    "ownership.transferred",
)

#: Phrasing for the UI. Kept here rather than in the frontend so the wording
#: cannot drift from what was actually recorded.
#:
#: This must cover every action string passed to audit.record anywhere in the
#: application. It previously covered twelve of them, so the other seventeen —
#: every MFA event, every denial, every dependency and policy change — reached
#: the audit log viewer as raw identifiers like "share.escalation_blocked"
#: sitting next to phrases like "revoked a share". tests/test_audit_labels.py
#: fails if a new action is added without a label here.
#: Labelled, but nothing in the application writes them yet. Kept because
#: CREDENTIAL_ACTIONS already filters for both and the wording is settled — but
#: named here so the map does not quietly imply the system records things it
#: does not. Delete from this set when the feature that writes them lands.
RESERVED = {"credential.viewed", "ownership.transferred"}

LABELS = {
    # credentials
    "credential.created": "created",
    "credential.viewed": "viewed",
    "credential.revealed": "revealed the secret",
    "credential.copied": "copied the secret",
    "credential.updated": "edited",
    "credential.rotated": "rotated the secret",
    "credential.rotation_impact": "recorded rotation impact",
    "credential.deleted": "deleted",
    "credential.tamper_detected": "INTEGRITY FAILURE",
    # oversight — an administrator acting on someone else's vault or account
    "credential.revealed_by_admin": "revealed someone else's secret as their administrator",
    "credential.changed_by_admin": "changed someone else's saved password",
    "vault.oversight_viewed": "looked through someone else's vault",
    "user.password_reset": "reset someone's sign-in password",

    # ── Everything outside the vault, recorded through app/core/activity.py ──

    # signing in
    "auth.signed_in": "signed in",
    "auth.sign_in_failed": "failed to sign in",
    "auth.signed_out": "signed out",
    "auth.password_changed": "changed their password",
    "auth.password_change_failed": "entered the wrong current password",

    # people and departments
    "user.created": "added an employee",
    "user.updated": "edited an employee",
    "user.deactivated": "deactivated an employee",
    "user.fingerprint_assigned": "assigned a fingerprint slot",
    "user.profile_updated": "updated their profile",
    "org_admin.created": "added an Org Admin",
    "org_admin.updated": "edited an Org Admin",
    "org_admin.deactivated": "deactivated an Org Admin",
    "department.created": "created a department",
    "department.renamed": "renamed a department",
    "department.deleted": "deleted a department",

    # leave, holidays and office hours
    "attendance.web_sign_in": "signed in (web clock)",
    "attendance.web_sign_out": "signed out (web clock)",
    "department.admin_assigned": "assigned a Department Admin",
    "organisation.admin_assigned": "assigned the Organisation Admin",
    "user.transferred": "moved someone to another department",
    "auth.password_reset_requested": "asked for a password reset",
    "user.hr_granted": "gave HR access",
    "user.hr_revoked": "removed HR access",
    "document.letterhead_updated": "updated the letterhead",
    "document.templates_added": "added letter templates",
    "document.template_updated": "edited a letter template",
    "letter.drafted": "drafted a letter",
    "letter.viewed": "opened a letter",
    "letter.edited": "edited a draft letter",
    "letter.discarded": "discarded a draft letter",
    "letter.issued": "issued a letter",
    "letter.revoked": "revoked a letter",
    "letter.downloaded": "downloaded a letter",
    "letter.acknowledged": "acknowledged a letter",
    "policy.published": "published a policy",
    "policy.updated": "changed a policy's details",
    "policy.downloaded": "downloaded a policy",
    "policy.reminded": "sent policy reminders",
    "policy.acknowledged": "acknowledged a policy",
    "document.filed": "filed an employee document",
    "document.renewed": "uploaded a renewed document",
    "document.updated": "changed a document's details",
    "document.downloaded": "downloaded an employee document",
    "payroll.component_created": "added a pay component",
    "payroll.component_updated": "changed a pay component",
    "payroll.profile_updated": "updated pay details",
    "payroll.salary_revised": "revised a salary",
    "payroll.run_prepared": "prepared payroll",
    "payroll.entry_adjusted": "adjusted a payslip",
    "payroll.run_submitted": "submitted payroll for approval",
    "payroll.run_approved": "approved and closed payroll",
    "payroll.run_returned": "sent payroll back to draft",
    "payroll.register_exported": "exported the payroll register",
    "payroll.payslip_downloaded": "downloaded a payslip",
    "reimbursement.submitted": "claimed an expense",
    "reimbursement.withdrawn": "withdrew an expense claim",
    "reimbursement.approved": "approved an expense claim",
    "reimbursement.rejected": "rejected an expense claim",
    "leave.requested": "requested leave",
    "leave.cancelled": "cancelled a leave request",
    "leave.approved": "approved leave",
    "leave.rejected": "rejected leave",
    "holiday.created": "added a holiday",
    "holiday.updated": "edited a holiday",
    "holiday.deleted": "removed a holiday",
    "settings.updated": "changed office hours",

    # devices and the organisation's key
    "device.created": "registered a device",
    "device.updated": "updated a device",
    "device.deleted": "removed a device",
    "device.command_sent": "sent a device command",
    "organisation.api_key_changed": "changed the organisation's API key",

    # tasks
    "task.created": "created a task",
    "task.updated": "edited a task",
    "task.deleted": "deleted a task",
    "task.commented": "commented on a task",
    "task.status_changed": "changed a task's status",
    "github.repo_added": "connected a GitHub repository",
    "github.repo_updated": "changed a GitHub repository's settings",
    "github.repo_removed": "disconnected a GitHub repository",
    "github.user_mapped": "linked a GitHub username",

    # sharing and ownership
    "share.granted": "shared",
    "share.revoked": "revoked a share",
    "share.expired": "access expired",
    "share.escalation_blocked": "blocked an attempt to grant more access than held",
    "ownership.transferred": "transferred ownership",

    # second factor
    "mfa.enrolment_started": "started authenticator setup",
    "mfa.enrolled": "enrolled an authenticator",
    "mfa.enrolment_failed": "failed authenticator setup",
    "mfa.verified": "passed a second-factor check",
    "mfa.failed": "failed a second-factor check",
    "mfa.step_up_required": "was asked for a second factor",
    "mfa.step_up_rejected": "was refused at the second-factor check",

    # authorisation
    "authz.denied": "was denied",

    # structure
    "rack.created": "created a rack",
    "system.created": "registered a system",
    "system.department_changed": "moved a system to another department",
    "dependency.linked": "linked a credential to a system",
    "dependency.unlinked": "unlinked a credential from a system",
    "rotation_policy.created": "set a rotation policy",
    "rotation_policy.deleted": "removed a rotation policy",

    # the log itself
    "audit.exported": "exported the audit log",

    # platform administration — a Super Admin acting on an organisation. Filed
    # under that organisation, so its own admins see what was done to it.
    "organisation.created": "created the organisation",
    "organisation.renamed": "renamed the organisation",
    "organisation.api_key_rotated": "issued the organisation a new API key",
    "organisation.delete_refused": "tried to delete the organisation while it still held data",
    "organisation.deleted": "deleted the organisation",
    "organisation.purged": "deleted the organisation and everything in it",
}

#: Namespace to category, so the viewer can group and colour rows without
#: parsing action strings in the browser. The namespace is already the grouping
#: the data carries; this just names it.
CATEGORIES = {
    "credential": "credential",
    "share": "access",
    "ownership": "access",
    "authz": "access",
    "mfa": "auth",
    "rack": "structure",
    "system": "structure",
    "dependency": "structure",
    "rotation_policy": "structure",
    "audit": "audit",
    "organisation": "platform",
    # Admin oversight of another person's vault.
    "vault": "access",
    # Outside the vault — see app/core/activity.py.
    "auth": "auth",
    "user": "people",
    "org_admin": "people",
    "department": "people",
    "attendance": "attendance",
    "payroll": "payroll",
    "letter": "documents",
    "policy": "documents",
    "document": "documents",
    "reimbursement": "payroll",
    "leave": "attendance",
    "holiday": "attendance",
    "settings": "attendance",
    "device": "devices",
    "task": "tasks",
    "github": "tasks",
}


def _label(action: str) -> str:
    """
    Human phrasing for an action.

    Unknown actions are humanised rather than passed through raw. A new action
    added elsewhere in the codebase should read as "did something plausible",
    not leak a dotted identifier into a compliance export — and the test that
    guards LABELS will catch it before anyone sees this fallback.
    """
    if action in LABELS:
        return LABELS[action]
    tail = action.split(".", 1)[-1]
    return tail.replace("_", " ")


def _category(action: str) -> str:
    return CATEGORIES.get(action.split(".", 1)[0], "other")


# ─── separate logs ───────────────────────────────────────────────────────────
#
# One stream of everything was unreadable: a payroll approval sat between
# forty letter downloads and a dozen sign-ins. The page now shows one log at
# a time. Each log is a set of categories, except "security", which cuts
# across them: anything refused, anything that errored, and tampering.
LOGS: dict[str, dict] = {
    "signins":      {"label": "Sign-ins",            "categories": ("auth",)},
    "people":       {"label": "People",              "categories": ("people",)},
    "attendance":   {"label": "Attendance & leave",  "categories": ("attendance",)},
    "payroll":      {"label": "Payroll",             "categories": ("payroll",)},
    "documents":    {"label": "HR documents",        "categories": ("documents",)},
    "vault":        {"label": "Vault & access",      "categories": ("credential", "access", "structure")},
    "devices":      {"label": "Devices",             "categories": ("devices",)},
    "tasks":        {"label": "Tasks",               "categories": ("tasks",)},
    "organisation": {"label": "Organisation",        "categories": ("platform", "audit", "other")},
    "security":     {"label": "Security alerts",     "categories": ()},
}

# Reading something, as opposed to changing it. Views and downloads are most
# of the volume and rarely what someone opens the log to find, so they can be
# shown on their own or left out.
_READ_PATTERNS = ("%.viewed", "%downloaded", "%exported", "%revealed%")


def _namespaces(categories) -> list[str]:
    return [ns for ns, cat in CATEGORIES.items() if cat in categories]


def category_condition(category: str):
    ns = _namespaces((category,))
    return or_(*[AuditLog.action.like(f"{n}.%") for n in ns]) if ns else AuditLog.id.is_(None)


def security_condition():
    return or_(AuditLog.result != "success", AuditLog.action == "credential.tamper_detected",
               AuditLog.action == "authz.denied", AuditLog.action == "auth.sign_in_failed")


def log_condition(log: str):
    """Which entries belong to one log. Unknown names match nothing."""
    spec = LOGS.get(log)
    if spec is None:
        return AuditLog.id.is_(None)
    if log == "security":
        return security_condition()
    known = _namespaces(spec["categories"])
    conds = [AuditLog.action.like(f"{n}.%") for n in known]
    if "other" in spec["categories"]:
        # Anything whose namespace no category claims ends up here, so no
        # entry is ever unreachable from the tabs.
        claimed = list(CATEGORIES)
        conds.append(~or_(*[AuditLog.action.like(f"{n}.%") for n in claimed]))
    return or_(*conds)


def is_read(action: str) -> bool:
    """The same rule as _READ_PATTERNS, for one action in Python."""
    return (action.endswith(".viewed") or action.endswith("downloaded")
            or action.endswith("exported") or "revealed" in action)


def kind_condition(kind: str | None):
    reads = or_(*[AuditLog.action.like(p) for p in _READ_PATTERNS])
    if kind == "reads":
        return reads
    if kind == "changes":
        return ~reads
    return None


def log_of(action: str, result: str = "success") -> str:
    cat = _category(action)
    for name, spec in LOGS.items():
        if cat in spec["categories"]:
            return name
    return "organisation"


def _row(e: AuditLog, names: dict[int, str] | None = None,
         orgs: dict[int, str] | None = None) -> dict:
    return {
        "seq": e.seq,
        "tenant_id": e.tenant_id,
        # Only filled for a Super Admin's all-organisations view, where rows
        # from different companies sit side by side.
        "organisation": (orgs or {}).get(e.tenant_id),
        "occurred_at": e.occurred_at,
        "actor_id": e.actor_id,
        "actor_name": (names or {}).get(e.actor_id),
        "actor_role": e.actor_role,
        "action": e.action,
        "label": _label(e.action),
        "category": _category(e.action),
        "log": log_of(e.action),
        "is_read": is_read(e.action),
        "result": e.result,
        "reason": e.reason,
        "target_type": e.target_type,
        "target_id": e.target_id,
        "source_ip": e.source_ip,
        "mfa_method": e.mfa_method,
        "details": e.details,
    }


async def _actor_names(db: AsyncSession, rows) -> dict[int, str]:
    """
    Current display names for the actors on this page of rows.

    Resolved at read time, not stored on the entry. The log records an id
    because that is the fact that cannot change; a name can be edited, and
    copying one into an immutable record would freeze a value that later
    disagrees with the user table. The trade is that these names are current
    rather than historical — the id beside them is what identifies the account.

    One query per page, bounded by the page size, rather than one per row.
    """
    ids = {e.actor_id for e in rows if e.actor_id is not None}
    if not ids:
        return {}

    result = await db.execute(
        select(User.id, User.name, User.email).where(User.id.in_(ids))
    )
    return {
        uid: (name or email or f"User {uid}")
        for uid, name, email in result.all()
    }


async def _org_names(db: AsyncSession, rows) -> dict[int, str]:
    """Organisation names for this page of rows — one query, page-bounded."""
    ids = {e.tenant_id for e in rows if e.tenant_id is not None}
    if not ids:
        return {}
    result = await db.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_(ids)))
    return dict(result.all())


def scope_conditions(ctx: SecurityContext, all_orgs: bool = False) -> list:
    """
    Which audit entries this person may read. One rule for the log, the
    action filter, the summary strip and the CSV export, so none of them can
    show more than the others.

        Super Admin    the organisation they are working in, or every
                       organisation with all_orgs
        Tenant Admin   their organisation
        anyone else    their organisation, narrowed to their department:
                       entries BY someone in it, or ABOUT someone in it,
                       their credentials, leave or tasks, the department's
                       systems, or the department itself

    The same department line as People and the Dependency Map. An Org Admin
    sees what happens in Operations — including a Tenant Admin acting on
    Operations' people — and nothing about Engineering. Organisation-wide
    entries (office hours, API key, other departments) stay with the Tenant
    Admin. Someone with no department sees only their own actions.
    """
    if ctx.permissions.grants_all:
        acting = getattr(ctx, "acting_tenant_id", None)
        if all_orgs or acting is None:
            return []
        return [AuditLog.tenant_id == acting]

    user = ctx.user
    in_tenant = AuditLog.tenant_id == user.tenant_id
    if user.role == "tenant_admin":
        return [in_tenant]

    if user.dept_id is None:
        return [in_tenant, AuditLog.actor_id == user.id]

    people = select(User.id).where(User.tenant_id == user.tenant_id, User.dept_id == user.dept_id)
    people_s = select(cast(User.id, String)).where(
        User.tenant_id == user.tenant_id, User.dept_id == user.dept_id)
    creds_s = select(cast(Credential.id, String)).where(
        Credential.tenant_id == user.tenant_id, Credential.owner_id.in_(people))
    systems_s = select(cast(System.id, String)).where(
        System.tenant_id == user.tenant_id, System.department_id == user.dept_id)
    leaves_s = select(cast(Leave.leave_id, String)).where(
        Leave.tenant_id == user.tenant_id, Leave.employee_id.in_(people))
    tasks_s = select(cast(Task.id, String)).where(
        Task.tenant_id == user.tenant_id,
        or_(Task.dept_id == user.dept_id, Task.assigned_to.in_(people)))

    # target_id is stored as text (it holds device names too), hence the casts.
    def about(kind, ids_as_text):
        return (AuditLog.target_type == kind) & AuditLog.target_id.in_(ids_as_text)

    return [
        in_tenant,
        or_(
            AuditLog.actor_id.in_(people),
            about("user", people_s),
            about("credential", creds_s),
            about("system", systems_s),
            about("leave", leaves_s),
            about("task", tasks_s),
            (AuditLog.target_type == "department") & (AuditLog.target_id == str(user.dept_id)),
        ),
    ]


@router.get("/credentials/{credential_id}/activity")
async def credential_activity(
    credential_id: int,
    limit: int = Query(100, le=500),
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    What has happened to this credential.

    Requires `view` on the credential itself, not just the role permission —
    otherwise the timeline would leak who holds access to something you cannot
    see.
    """
    credential = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="view",
        grants_all=ctx.permissions.grants_all,
    )

    rows = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.target_type == "credential",
                AuditLog.target_id == str(credential_id),
                AuditLog.action.in_(CREDENTIAL_ACTIONS),
            )
            .order_by(AuditLog.occurred_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [_row(e, await _actor_names(db, rows)) for e in rows]


@router.get("/audit")
async def audit_log(
    actor_id: int | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    result: str | None = None,
    category: str | None = None,
    log: str | None = None,
    kind: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    all_orgs: bool = False,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    ctx: SecurityContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    The audit log, filtered.

    `log` picks one of the separate logs (LOGS); `kind` is "changes" or
    "reads" (views and downloads).

    Scoped by scope_conditions: organisation for a Tenant Admin, department
    for everyone else, everything for a Super Admin.
    """
    q = select(AuditLog)
    count_q = select(func.count(AuditLog.id))

    conditions = list(scope_conditions(ctx, all_orgs))
    if actor_id is not None:
        conditions.append(AuditLog.actor_id == actor_id)
    if action:
        conditions.append(AuditLog.action == action)
    if target_type:
        conditions.append(AuditLog.target_type == target_type)
    if target_id:
        conditions.append(AuditLog.target_id == str(target_id))
    if result:
        conditions.append(AuditLog.result == result)
    if category:
        # A category is a set of namespaces ("people" = user, org_admin,
        # department). An unknown one matches nothing rather than everything.
        conditions.append(category_condition(category))
    if log:
        conditions.append(log_condition(log))
    if kind_condition(kind) is not None:
        conditions.append(kind_condition(kind))
    if since:
        conditions.append(AuditLog.occurred_at >= since)
    if until:
        conditions.append(AuditLog.occurred_at <= until)

    for c in conditions:
        q = q.where(c)
        count_q = count_q.where(c)

    total = (await db.execute(count_q)).scalar_one()
    rows = (
        await db.execute(
            q.order_by(AuditLog.occurred_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    names = await _actor_names(db, rows)
    orgs = await _org_names(db, rows) if ctx.permissions.grants_all else {}

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": [_row(e, names, orgs) for e in rows],
    }


@router.get("/audit/actions")
async def known_actions(
    all_orgs: bool = False,
    log: str | None = None,
    ctx: SecurityContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Distinct actions present, so the filter dropdown reflects reality."""
    q = select(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action)
    for c in scope_conditions(ctx, all_orgs):
        q = q.where(c)
    if log:
        q = q.where(log_condition(log))

    rows = (await db.execute(q.order_by(AuditLog.action))).all()
    return [
        {"action": a, "count": n, "label": _label(a), "category": _category(a), "log": log_of(a)}
        for a, n in rows
    ]


@router.get("/audit/export.csv")
async def export_csv(
    since: datetime | None = None,
    until: datetime | None = None,
    action: str | None = None,
    actor_id: int | None = None,
    log: str | None = None,
    kind: str | None = None,
    all_orgs: bool = False,
    ctx: SecurityContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    Export as CSV.

    Capped at 50,000 rows: an unbounded export on a busy log would hold a
    connection open long enough to look like an outage. Narrow the date range
    for more.

    The export itself is audited — bulk-reading the audit log is exactly the
    kind of action the audit log exists to record.
    """
    q = select(AuditLog)
    for c in scope_conditions(ctx, all_orgs):
        q = q.where(c)
    if since:
        q = q.where(AuditLog.occurred_at >= since)
    if until:
        q = q.where(AuditLog.occurred_at <= until)
    if action:
        q = q.where(AuditLog.action == action)
    if actor_id is not None:
        q = q.where(AuditLog.actor_id == actor_id)
    if log:
        q = q.where(log_condition(log))
    if kind_condition(kind) is not None:
        q = q.where(kind_condition(kind))

    rows = (
        await db.execute(q.order_by(AuditLog.seq.asc()).limit(50_000))
    ).scalars().all()

    await audit.record(
        db,
        action="audit.exported",
        target_type="audit_log",
        details={
            "rows": len(rows),
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        **ctx.audit_kwargs(),
    )
    await db.commit()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "seq", "occurred_at", "tenant_id", "actor_id", "actor_role", "action",
        "target_type", "target_id", "result", "reason", "source_ip",
        "mfa_method", "hash",
    ])
    for e in rows:
        writer.writerow([
            e.seq, e.occurred_at.isoformat(), e.tenant_id, e.actor_id,
            e.actor_role, e.action, e.target_type, e.target_id, e.result,
            e.reason, e.source_ip, e.mfa_method, e.hash,
        ])
    buffer.seek(0)

    # The hash column is included deliberately: an exported file can be
    # re-verified against the live chain later.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{stamp}.csv"'},
    )


@router.get("/audit/integrity")
async def integrity(
    ctx: SecurityContext = Depends(require_permission("audit.verify")),
    db: AsyncSession = Depends(get_db),
):
    """
    Walk the hash chain and report whether it holds.

    What a pass means, precisely: no entry has been altered or removed by
    anyone who could not also recompute every subsequent hash. It does NOT
    prove the log is complete — an attacker holding the database owner
    credentials could rebuild the whole chain consistently.

    Closing that gap needs the head hash anchored somewhere the application
    cannot reach. `anchor` below is what you publish. SECURITY.md §5.3.
    """
    result = await audit.verify_chain(db)
    total = await audit.count(db)
    head = await audit.head_hash(db)

    return {
        **result,
        "entries": total,
        "anchor": head,
        "caveat": (
            "A pass proves no entry was altered without recomputing every "
            "later hash. It does not prove completeness — anchor the head "
            "externally for that."
        ),
    }


@router.get("/audit/summary")
async def summary(
    days: int = Query(7, le=90),
    all_orgs: bool = False,
    ctx: SecurityContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Counts by action and by result, for a dashboard strip."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = select(AuditLog).where(AuditLog.occurred_at >= since)
    for c in scope_conditions(ctx, all_orgs):
        base = base.where(c)
    sub = base.subquery()

    by_action = (
        await db.execute(
            select(sub.c.action, func.count()).group_by(sub.c.action)
            .order_by(func.count().desc()).limit(10)
        )
    ).all()
    by_result = (
        await db.execute(select(sub.c.result, func.count()).group_by(sub.c.result))
    ).all()

    counts = dict(by_result)

    # How much is in each log over the period, for the tab badges. One query
    # per log keeps every count defined by exactly the condition the tab uses.
    by_log = {}
    for name in LOGS:
        q = select(func.count(AuditLog.id)).where(AuditLog.occurred_at >= since, log_condition(name))
        for c in scope_conditions(ctx, all_orgs):
            q = q.where(c)
        by_log[name] = (await db.execute(q)).scalar_one()

    return {
        "days": days,
        "logs": [{"log": k, "label": v["label"], "count": by_log[k]} for k, v in LOGS.items()],
        "by_action": [
            {"action": a, "label": _label(a), "count": n} for a, n in by_action
        ],
        "success": counts.get("success", 0),
        # Denials are the interesting number — a spike is what probing looks
        # like, and it is the reason denied attempts are logged at all.
        "denied": counts.get("denied", 0),
        "errors": counts.get("error", 0),
    }
