"""The whole organisation on the sign-in clock, one day. See routes/clock.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_tenant_api_key
from app.api.routes.clock import _day
from app.db.session import get_db
from app.models.domain import Tenant
from app.services import clock_service

router = APIRouter()


@router.get("/clock/team")
async def organisation_day(date: str | None = None,
                           tenant: Tenant = Depends(verify_tenant_api_key),
                           db: AsyncSession = Depends(get_db)):
    """Tenant Admin by API key or password, or a Super Admin acting within it."""
    return await clock_service.team_for(db, tenant.id, None, _day(date))
