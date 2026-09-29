"""Security assessment and rotation policies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import SecurityContext, require_permission
from app.core import audit
from app.db.session import get_db
from app.models.credentials import Credential, Rack, RotationPolicy, Vault
from app.services import scoring_service as sc
from app.services import vault_service as svc

router = APIRouter()


class PolicyIn(BaseModel):
    interval_days: int = Field(90, gt=0, le=3650)
    warn_days_before: int = Field(14, ge=0, le=365)
    credential_id: int | None = None
    rack_id: int | None = None
    enabled: bool = True


@router.get("/credentials/{credential_id}/security")
async def credential_security(
    credential_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """Findings for one credential, with the facts behind them."""
    credential = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="view",
        grants_all=ctx.permissions.grants_all,
    )
    return (await sc.assess(db, credential)).as_dict()


@router.get("/security/overview")
async def security_overview(
    severity: str | None = Query(None, description="critical | warning | healthy"),
    limit: int = Query(200, le=500),
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    Every credential the caller can see, assessed.

    Assessed per credential rather than with one clever aggregate query. That
    is several round trips, which is why it is capped — but the rules read
    facts a single SQL statement cannot express without becoming unmaintainable,
    and correctness here matters more than speed. If this becomes slow enough
    to notice, cache the assessment and refresh it on change, rather than
    rewriting the rules in SQL.
    """
    credentials = await svc.list_credentials(
        db, user=ctx.user, grants_all=ctx.permissions.grants_all, limit=limit,
    )

    results = [(await sc.assess(db, c)).as_dict() for c in credentials]
    if severity:
        results = [r for r in results if r["severity"] == severity]

    counts = {"critical": 0, "warning": 0, "healthy": 0}
    for r in results:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1

    # Worst first: a list that opens on healthy items buries the point.
    order = {"critical": 0, "warning": 1, "healthy": 2}
    results.sort(key=lambda r: (order.get(r["severity"], 9), r["name"]))

    return {"counts": counts, "assessed": len(results), "credentials": results}


@router.get("/security/thresholds")
async def thresholds(
    ctx: SecurityContext = Depends(require_permission("credential.view")),
):
    """
    The values the rules use. Exposed so the UI can explain a finding in terms
    of the configured limit rather than a hardcoded number in two places.
    """
    t = sc.DEFAULT_THRESHOLDS
    return {
        "password_age_warning_days": t.password_age_warning_days,
        "password_age_critical_days": t.password_age_critical_days,
        "rotation_overdue_critical_days": t.rotation_overdue_critical_days,
        "excessive_share_count": t.excessive_share_count,
        "unreviewed_days": t.unreviewed_days,
        "kinds_expecting_2fa": list(t.kinds_expecting_2fa),
        "documentation": "docs/SCORING.md",
    }


@router.post("/security/rotation-policies", status_code=201)
async def create_policy(
    data: PolicyIn,
    ctx: SecurityContext = Depends(require_permission("credential.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Attach a rotation policy to one credential, or to a whole rack."""
    if (data.credential_id is None) == (data.rack_id is None):
        raise HTTPException(400, "Set exactly one of credential_id or rack_id.")

    if data.credential_id:
        credential = await svc.get_credential(db, data.credential_id)
        await svc.require_level(
            db, user=ctx.user, credential=credential, required="edit",
            grants_all=ctx.permissions.grants_all,
        )
        tenant_id = credential.tenant_id
    else:
        rack = (
            await db.execute(
                select(Rack).join(Vault, Vault.id == Rack.vault_id).where(
                    Rack.id == data.rack_id,
                    Vault.tenant_id == ctx.user.tenant_id,
                )
            )
        ).scalars().first()
        if not rack:
            raise HTTPException(404, "Rack not found.")
        tenant_id = ctx.user.tenant_id

    policy = RotationPolicy(
        tenant_id=tenant_id,
        credential_id=data.credential_id,
        rack_id=data.rack_id,
        interval_days=data.interval_days,
        warn_days_before=data.warn_days_before,
        enabled=data.enabled,
    )
    db.add(policy)
    await db.flush()

    await audit.record(
        db,
        action="rotation_policy.created",
        target_type="credential" if data.credential_id else "rack",
        target_id=data.credential_id or data.rack_id,
        details={"interval_days": data.interval_days},
        **ctx.audit_kwargs(),
    )
    await db.commit()

    return {
        "id": policy.id,
        "interval_days": policy.interval_days,
        "warn_days_before": policy.warn_days_before,
        "credential_id": policy.credential_id,
        "rack_id": policy.rack_id,
    }


@router.get("/security/rotation-policies")
async def list_policies(
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(RotationPolicy).where(RotationPolicy.tenant_id == ctx.user.tenant_id)
        )
    ).scalars().all()
    return [
        {
            "id": p.id,
            "credential_id": p.credential_id,
            "rack_id": p.rack_id,
            "interval_days": p.interval_days,
            "warn_days_before": p.warn_days_before,
            "enabled": p.enabled,
        }
        for p in rows
    ]


@router.delete("/security/rotation-policies/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.edit")),
    db: AsyncSession = Depends(get_db),
):
    policy = (
        await db.execute(
            select(RotationPolicy).where(
                RotationPolicy.id == policy_id,
                RotationPolicy.tenant_id == ctx.user.tenant_id,
            )
        )
    ).scalars().first()
    if not policy:
        raise HTTPException(404, "Policy not found.")

    await db.delete(policy)
    await audit.record(
        db, action="rotation_policy.deleted", target_type="rotation_policy",
        target_id=policy_id, **ctx.audit_kwargs(),
    )
    await db.commit()
