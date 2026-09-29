"""Systems, dependency links, and the blast-radius preview."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import SecurityContext, require_permission
from app.db.session import get_db
from app.models.credentials import System
from app.services import dependency_service as deps
from app.services import vault_service as svc

router = APIRouter()


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
    """

    notes: str | None = None


@router.get("/systems")
async def list_systems(
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    return {
        "systems": await deps.list_systems(db, tenant_id=ctx.user.tenant_id),
        "suggested_kinds": list(deps.COMMON_KINDS),
    }


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
    return await deps.for_credential(db, credential_id)


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
        db, ctx=ctx, name=data.name, kind=data.kind,
        environment=data.environment, description=data.description,
    )
    dep = await deps.link(db, ctx=ctx, credential=credential, system=system,
                          notes=data.notes)
    await db.commit()

    return {
        "dependency_id": dep.id,
        "system_id": system.id,
        "name": system.name,
        "environment": system.environment,
    }


@router.delete("/dependencies/{dependency_id}", status_code=204)
async def remove_dependency(
    dependency_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.edit")),
    db: AsyncSession = Depends(get_db),
):
    await deps.unlink(db, ctx=ctx, dependency_id=dependency_id)
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
    """
    if action not in ("rotate", "revoke"):
        raise HTTPException(400, "action must be 'rotate' or 'revoke'.")

    credential = await svc.get_credential(db, credential_id)
    await svc.require_level(
        db, user=ctx.user, credential=credential, required="view",
        grants_all=ctx.permissions.grants_all,
    )
    return await deps.impact_of(db, credential=credential, action=action)


@router.get("/dependency-graph")
async def dependency_graph(
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    The org-wide map: credentials, systems, and the links between them.

    Bipartite — edges only ever run credential→system — which is what lets the
    UI draw it as two columns instead of needing a layout engine.
    """
    return await deps.org_graph(db, tenant_id=ctx.user.tenant_id)


@router.get("/systems/{system_id}/credentials")
async def system_credentials(
    system_id: int,
    ctx: SecurityContext = Depends(require_permission("credential.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    Which credentials a system needs — the reverse lookup.

    Answers "we are rebuilding this server, what secrets does it want", which
    is the question people actually arrive with.
    """
    system = (
        await db.execute(
            select(System).where(
                System.id == system_id, System.tenant_id == ctx.user.tenant_id
            )
        )
    ).scalars().first()
    if not system:
        raise HTTPException(404, "System not found.")

    graph = await deps.org_graph(db, tenant_id=ctx.user.tenant_id)
    ids = {e["credential_id"] for e in graph["edges"] if e["system_id"] == system_id}

    return {
        "system": {
            "id": system.id, "name": system.name,
            "kind": system.kind, "environment": system.environment,
        },
        "credentials": [c for c in graph["credentials"] if c["id"] in ids],
    }
