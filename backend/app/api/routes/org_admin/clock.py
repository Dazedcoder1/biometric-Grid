"""An Org Admin's department on the sign-in clock, one day. See routes/clock.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.api.routes.clock import _day
from app.db.session import get_db
from app.models.domain import User
from app.services import clock_service

router = APIRouter()


@router.get("/clock/team")
async def department_day(date: str | None = None,
                         current_user: User = Depends(require_role("org_admin")),
                         db: AsyncSession = Depends(get_db)):
    """Their own department, nobody else's."""
    if current_user.dept_id is None:
        raise HTTPException(409, "You are not assigned to a department yet.")
    return await clock_service.team_for(db, current_user.tenant_id, current_user.dept_id, _day(date))
