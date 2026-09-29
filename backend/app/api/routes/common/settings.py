"""
Office-hours settings, readable by anyone signed in.

Why this exists as its own route rather than one per role: office hours are a
single tenant-wide fact that every attendance screen needs in order to say
anything at all — whether an arrival was late, whether a day met the minimum,
what the working week is. The only way to read it was
`GET /api/tenant/settings`, which authenticates through `verify_tenant_api_key`
and answers a non-tenant-admin with

    "This area is for Tenant Admins ... you are signed in as 'org_admin'."

So the Org Admin attendance pages, the Today board and the employee attendance
page all asked for settings, all got 403, and all quietly fell back to their own
hardcoded defaults. The numbers on screen looked authoritative and were not
coming from the database at all. A third route,
`/api/tenant/settings/public`, was referenced by the frontend and had never
been written, so it 404'd into the same silent fallback.

One read endpoint for every authenticated role replaces all three. Writing
stays where it was — office hours are tenant-wide configuration, and an Org
Admin changing them would silently repoint every other department's
attendance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.domain import Settings, User

router = APIRouter()

#: Used when a tenant has no settings row yet. Matches the column defaults in
#: models/domain.py — the two must agree, or a tenant's figures would change
#: the first time anyone opened the Settings page and saved.
DEFAULTS = {
    "office_start_time": "09:00:00",
    "office_end_time": "18:00:00",
    "late_threshold_minutes": 15,
    "working_days": "1,2,3,4,5",
    "min_working_hours": 9.0,
}


def _out(row: Settings | None) -> dict:
    if row is None:
        return {**DEFAULTS, "is_default": True}
    return {
        "office_start_time": row.office_start_time or DEFAULTS["office_start_time"],
        "office_end_time": row.office_end_time or DEFAULTS["office_end_time"],
        "late_threshold_minutes": (
            row.late_threshold_minutes
            if row.late_threshold_minutes is not None
            else DEFAULTS["late_threshold_minutes"]
        ),
        "working_days": row.working_days or DEFAULTS["working_days"],
        "min_working_hours": (
            row.min_working_hours
            if row.min_working_hours is not None
            else DEFAULTS["min_working_hours"]
        ),
        # Lets the interface distinguish "nobody has configured this yet" from
        # "these are the configured values". Previously both looked identical,
        # which is how a 403 masquerading as defaults went unnoticed.
        "is_default": False,
    }


@router.get("/settings")
async def read_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    This tenant's office hours.

    Scoped to the caller's own tenant and carrying no secrets — office hours
    are not confidential, and every role needs them to make sense of an
    attendance screen.
    """
    row = (
        await db.execute(
            select(Settings).where(Settings.tenant_id == current_user.tenant_id)
        )
    ).scalars().first()
    return _out(row)
