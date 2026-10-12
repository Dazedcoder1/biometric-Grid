"""
The web sign-in clock — Sign In / Sign Out from the browser.

    /api/clock/today      my day so far: status, sessions, hours
    /api/clock/in         sign in
    /api/clock/out        sign out
    /api/clock/history    my last N days

    /api/org/clock/team      an Org Admin's department, one day
                             (routes/org_admin/clock.py)
    /api/tenant/clock/team   the whole organisation, one day — Tenant Admin,
                             or a Super Admin acting within it
                             (routes/tenant/clock.py)

Web punches and fingerprint punches land in the same table and the same day,
so the two can be mixed freely — see services/clock_service.py.

Every web punch is written to the audit log with the address it came from, so
a sign-in from somewhere unexpected can be found later. There is no location
restriction: anyone can sign in from anywhere, and the record says where.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core import activity
from app.core.activity import _client_ip
from app.db.session import get_db
from app.models.domain import AttendanceLog, User
from app.services import clock_service

router = APIRouter()

WEB_DEVICE = "web"


def _clock_user(user: User) -> User:
    """Only people who belong to an organisation keep attendance."""
    if user.tenant_id is None:
        raise HTTPException(
            409,
            "The sign-in clock is for people in an organisation. A platform "
            "Super Admin does not keep attendance.",
        )
    return user


def _hhmm(iso: str | None) -> str:
    if not iso:
        return ""
    return dt.datetime.fromisoformat(iso).astimezone(clock_service.zone()).strftime("%H:%M")


async def _punch(db: AsyncSession, request: Request, user: User, kind: str) -> dict:
    now = clock_service.now_utc()
    today = await clock_service.today_for(db, user, now)

    if kind == "IN" and today["status"] == "in":
        raise HTTPException(409, f"You are already signed in, since {_hhmm(today['signed_in_since'])}.")
    if kind == "OUT" and today["status"] != "in":
        raise HTTPException(409, "You are not signed in.")

    ip = _client_ip(request)
    db.add(AttendanceLog(
        tenant_id=user.tenant_id,
        device_id=WEB_DEVICE,
        user_id=user.id,
        finger_id=None,
        record_type=kind,
        timestamp=now,
        source="web",
        source_ip=(ip or "")[:64] or None,
    ))
    if kind == "IN":
        await activity.log(
            db, request, action="attendance.web_sign_in", tenant_id=user.tenant_id,
            target_type="user", target_id=user.id, actor=user, details={"name": user.name},
        )
    else:
        await activity.log(
            db, request, action="attendance.web_sign_out", tenant_id=user.tenant_id,
            target_type="user", target_id=user.id, actor=user, details={"name": user.name},
        )
    await db.commit()
    return await clock_service.today_for(db, user, now)


# ─── my clock ────────────────────────────────────────────────────────────────

@router.get("/today")
async def my_today(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await clock_service.today_for(db, _clock_user(current_user))


@router.post("/in")
async def sign_in(request: Request, current_user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    return await _punch(db, request, _clock_user(current_user), "IN")


@router.post("/out")
async def sign_out(request: Request, current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    return await _punch(db, request, _clock_user(current_user), "OUT")


@router.get("/history")
async def my_history(days: int = Query(30, ge=1, le=90),
                     current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return {"days": await clock_service.history_for(db, _clock_user(current_user), days),
            "timezone": clock_service.settings.APP_TIMEZONE}


# ─── team views ──────────────────────────────────────────────────────────────

def _day(raw: str | None) -> dt.date:
    if not raw:
        return clock_service.local_today()
    try:
        day = dt.date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD.") from None
    if day > clock_service.local_today():
        raise HTTPException(400, "That date is in the future.")
    return day
