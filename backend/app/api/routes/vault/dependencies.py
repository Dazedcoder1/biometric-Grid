"""
Systems, dependency links, and the blast-radius preview.

Scoped by department: a Tenant Admin sees every system in the organisation;
everyone else sees their own department's systems plus shared ones. The rule
lives in dependency_service.Scope and every route here goes through it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import SecurityContext, require_organisation, require_permission
from app.db.session import get_db
from app.models.credentials import Credential, CredentialDependency
from app.services import dependency_service as deps
from app.services import vault_service as svc

router = APIRouter()


def _scope(ctx: SecurityContext) -> deps.Scope:
    # A Super Admin works in the organisation named by X-Acting-Tenant-Id;
    # without one there is no map to draw, so ask them to choose (409).
    tenant = require_organisation(ctx)
    return deps.scope_for(ctx.user, grants_all=ctx.permissions.grants_all, tenant_id=tenant)


class SystemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    kind: str | None = Field(None, max_length=64)
    environment: str | None = Field(None, max_length=32)
    description: str | None = None


class LinkIn(SystemIn):
    """
    Link by name, creating the system if needed.

    Taking a name rather than an id is deliberate: the user's intent is "this
    credential is used by production-postgres", and making them create the
    system first is a step that exists only for the database's benefit.

    `department_id` is optional. Left out, a new system goes in your own
    department (a Tenant Admin's goes in shared). Sent as null, it is shared.
    """

    notes: str | None = None
    department_id: int | None = None


class MoveIn(BaseModel):
    # null = shared with the whole organisation
    department_id: int | None


@router.get("/systems")
async def list_systems(
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    scope = _scope(ctx)
    return {
        "systems": await deps.list_systems(db, scope=scope),
        "suggested_kinds": list(deps.COMMON_KINDS),
        "departments": await deps.assignable_departments(db, scope=scope),
        "all_departments": scope.all_departments,
    }


@router.patch("/systems/{system_id}")
async def move_system(
    system_id: int,
    data: MoveIn,
    ctx: SecurityContext = Depends(require_permission("system.manage")),
    db: AsyncSession = Depends(get_db),
):
    """
    Put a system in a department, or make it shared (department_id: null).

    Tenant Admin: any department in the organisation. Org Admin: only between
    their own department and shared.
    """
    scope = _scope(ctx)
    system = await deps.move_system(
        db, ctx=ctx, scope=scope, system_id=system_id, department_id=data.department_id,
    )
    await db.commit()
    names = await deps._department_names(db, scope.tenant_id)
    return deps._system_out(system, names)


@router.get("/credentials/{credential_id}/dependencies")
async def credential_dependencies(
    credential_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    credential = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="view",
        grants_all=ctx.permissions.grants_all,
    )
    return await deps.for_credential(db, credential_id, scope=_scope(ctx))


@router.post("/credentials/{credential_id}/dependencies", status_code=201)
async def add_dependency(
    credential_id: int,
    data: LinkIn,
    ctx: SecurityContext = Depends(require_permission("credential.edit")),
    db: AsyncSession = Depends(get_db),
):
    credential = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="edit",
        grants_all=ctx.permissions.grants_all,
    )

    system = await deps.upsert_system(
        db, ctx=ctx, scope=_scope(ctx), name=data.name, kind=data.kind,
        environment=data.environment, description=data.description,
        department_id=data.department_id,
        department_given="department_id" in data.model_fields_set,
    )
    dep = await deps.link(db, ctx=ctx, credential=credential, system=system,
                          notes=data.notes)
    await db.commit()

    return {
        "dependency_id": dep.id,
        "system_id": system.id,
        "name": system.name,
        "environment": system.environment,
        "department_id": system.department_id,
    }


@router.delete("/dependencies/{dependency_id}", status_code=204)
async def remove_dependency(
    dependency_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.edit")),
    db: AsyncSession = Depends(get_db),
):
    # The link must be in your organisation, on a system you can see, and on
    # a credential you may edit. It used to be fetched by id alone.
    dependency, credential = await deps.get_dependency(
        db, scope=_scope(ctx), dependency_id=dependency_id,
    )
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="edit",
        grants_all=ctx.permissions.grants_all,
    )
    await deps.unlink(db, ctx=ctx, dependency=dependency)
    await db.commit()


@router.get("/credentials/{credential_id}/impact")
async def impact(
    credential_id: int,
    action: str = Query("rotate", description="rotate | revoke"),
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    What breaks if this credential is rotated or revoked.

    Called BEFORE the action, so the answer arrives while it can still change
    the decision. Systems break on rotation; people lose access on revocation —
    reported separately, because a warning about the wrong one is worse than
    none.

    Lists systems in every department, not just yours — see
    dependency_service's docstring for why.
    """
    if action not in ("rotate", "revoke"):
        raise HTTPException(400, "action must be 'rotate' or 'revoke'.")

    credential = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="view",
        grants_all=ctx.permissions.grants_all,
    )
    return await deps.impact_of(db, credential=credential, action=action, scope=_scope(ctx))


@router.get("/dependency-graph")
async def dependency_graph(
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    The map: credentials, systems, and the links between them — as far as
    this person's departments reach.

    Bipartite — edges only ever run credential→system — which is what lets the
    UI draw it as two columns instead of needing a layout engine.
    """
    graph = await deps.org_graph(db, scope=_scope(ctx), user=ctx.user)
    graph["can_move_systems"] = ctx.permissions.has("system.manage")
    graph["departments"] = await deps.assignable_departments(db, scope=_scope(ctx))
    return graph


@router.get("/systems/{system_id}/credentials")
async def system_credentials(
    system_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    Which credentials a system needs — the reverse lookup.

    Answers "we are rebuilding this server, what secrets does it want", which
    is the question people actually arrive with. The system must be one you can
    see; names only, never secrets.
    """
    scope = _scope(ctx)
    system = await deps.get_visible_system(db, scope=scope, system_id=system_id)

    rows = (
        await db.execute(
            select(Credential.id, Credential.name, Credential.kind)
            .join(CredentialDependency, CredentialDependency.credential_id == Credential.id)
            .where(
                CredentialDependency.system_id == system.id,
                Credential.tenant_id == scope.tenant_id,
                Credential.deleted_at.is_(None),
            )
            .order_by(Credential.name)
        )
    ).all()
    names = await deps._department_names(db, scope.tenant_id)
    return {
        "system": deps._system_out(system, names),
        "credentials": [{"id": i, "name": n, "kind": k} for i, n, k in rows],
    }
