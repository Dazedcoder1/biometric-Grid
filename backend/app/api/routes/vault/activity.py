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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import (
    SecurityContext,
    require_permission,
)
from app.core import audit
from app.db.session import get_db
from app.models.domain import User
from app.models.security import AuditLog
from app.services import vault_service as svc

router = APIRouter()

#: Actions that belong on a credential's timeline. Everything else in the audit
#: log — logins, MFA, role changes — is noise at this zoom level.
CREDENTIAL_ACTIONS = (
    "credential.created", "credential.viewed", "credential.revealed",
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
    "dependency.linked": "linked a credential to a system",
    "dependency.unlinked": "unlinked a credential from a system",
    "rotation_policy.created": "set a rotation policy",
    "rotation_policy.deleted": "removed a rotation policy",

    # the log itself
    "audit.exported": "exported the audit log",
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


def _row(e: AuditLog, names: dict[int, str] | None = None) -> dict:
    return {
        "seq": e.seq,
        "occurred_at": e.occurred_at,
        "actor_id": e.actor_id,
        "actor_name": (names or {}).get(e.actor_id),
        "actor_role": e.actor_role,
        "action": e.action,
        "label": _label(e.action),
        "category": _category(e.action),
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
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    ctx: SecurityContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    The audit log, filtered.

    Scoped to the caller's tenant unless they hold `grants_all`. Without that
    scoping, `audit.view` on one tenant would expose every other tenant's
    activity.
    """
    q = select(AuditLog)
    count_q = select(func.count(AuditLog.id))

    conditions = []
    if not ctx.permissions.grants_all:
        conditions.append(AuditLog.tenant_id == ctx.user.tenant_id)
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

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": [_row(e, names) for e in rows],
    }


@router.get("/audit/actions")
async def known_actions(
    ctx: SecurityContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Distinct actions present, so the filter dropdown reflects reality."""
    q = select(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action)
    if not ctx.permissions.grants_all:
        q = q.where(AuditLog.tenant_id == ctx.user.tenant_id)

    rows = (await db.execute(q.order_by(AuditLog.action))).all()
    return [
        {"action": a, "count": n, "label": _label(a), "category": _category(a)}
        for a, n in rows
    ]


@router.get("/audit/export.csv")
async def export_csv(
    since: datetime | None = None,
    until: datetime | None = None,
    action: str | None = None,
    actor_id: int | None = None,
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
    if not ctx.permissions.grants_all:
        q = q.where(AuditLog.tenant_id == ctx.user.tenant_id)
    if since:
        q = q.where(AuditLog.occurred_at >= since)
    if until:
        q = q.where(AuditLog.occurred_at <= until)
    if action:
        q = q.where(AuditLog.action == action)
    if actor_id is not None:
        q = q.where(AuditLog.actor_id == actor_id)

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
    ctx: SecurityContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Counts by action and by result, for a dashboard strip."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base = select(AuditLog).where(AuditLog.occurred_at >= since)
    if not ctx.permissions.grants_all:
        base = base.where(AuditLog.tenant_id == ctx.user.tenant_id)
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
    return {
        "days": days,
        "by_action": [
            {"action": a, "label": _label(a), "count": n} for a, n in by_action
        ],
        "success": counts.get("success", 0),
        # Denials are the interesting number — a spike is what probing looks
        # like, and it is the reason denied attempts are logged at all.
        "denied": counts.get("denied", 0),
        "errors": counts.get("error", 0),
    }
