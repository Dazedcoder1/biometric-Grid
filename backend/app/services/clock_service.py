"""
The sign-in clock: turning punches into a working day.

A punch is one attendance_logs row, IN or OUT, from a fingerprint scanner or
the web Sign In button. A day is the person's punches between local midnight
and the next, paired into sessions:

    IN 09:02 (web)  OUT 13:05 (scanner)  IN 13:48 (scanner)  OUT 18:31 (web)
    -> two sessions, effective 8h 50m, gross 9h 29m

  effective   time actually signed in: the sum of the sessions, with an open
              session counted up to now.
  gross       first sign-in to last sign-out (or to now while signed in).

Pairing is deliberately forgiving, because scanners double-read and offline
sync replays every punch as IN:
  - an IN while already signed in is ignored (the earlier one stands);
  - an OUT while signed out is ignored.
So a stray punch can never produce negative or doubled time.

"Today" is local to APP_TIMEZONE, not the server's UTC — see config.py.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.models.domain import AttendanceLog, User

logger = logging.getLogger(__name__)

UTC = dt.UTC


def zone() -> dt.tzinfo:
    try:
        return ZoneInfo(settings.APP_TIMEZONE or "UTC")
    except Exception:  # noqa: BLE001 — a typo in .env must not stop attendance
        logger.error("APP_TIMEZONE %r is not a known time zone; using UTC.", settings.APP_TIMEZONE)
        return UTC


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def aware(ts: dt.datetime) -> dt.datetime:
    """Scanner rows were written with naive server time, which is UTC."""
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def local_today(now: dt.datetime | None = None) -> dt.date:
    return (now or now_utc()).astimezone(zone()).date()


def day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Local midnight to local midnight, as UTC instants."""
    tz = zone()
    start = dt.datetime.combine(day, dt.time.min, tzinfo=tz)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def _iso(ts: dt.datetime | None) -> str | None:
    return ts.astimezone(UTC).isoformat() if ts else None


def summarise(punches, now: dt.datetime, *, is_today: bool) -> dict:
    """
    One person's day from their punches, oldest first or not.

    `punches` are objects with timestamp, record_type and source. An open
    session on a past day is reported as unclosed and counts no time — the
    person forgot to sign out, and inventing an end would be guessing.
    """
    sessions: list[dict] = []
    current: dict | None = None
    for p in sorted(punches, key=lambda x: aware(x.timestamp)):
        ts = aware(p.timestamp)
        source = getattr(p, "source", None) or "device"
        if p.record_type == "IN":
            if current is None:
                current = {"in": ts, "in_source": source, "out": None, "out_source": None}
        elif p.record_type == "OUT" and current is not None:
            current["out"], current["out_source"] = ts, source
            sessions.append(current)
            current = None
    if current is not None:
        sessions.append(current)

    effective = 0.0
    for s in sessions:
        end = s["out"] or (now if is_today else None)
        if end:
            effective += max(0.0, (end - s["in"]).total_seconds())

    signed_in = bool(sessions) and sessions[-1]["out"] is None and is_today
    unclosed = bool(sessions) and sessions[-1]["out"] is None and not is_today
    first_in = sessions[0]["in"] if sessions else None
    closed_outs = [s["out"] for s in sessions if s["out"]]
    last_out = closed_outs[-1] if closed_outs else None
    gross_end = now if signed_in else last_out
    gross = max(0.0, (gross_end - first_in).total_seconds()) if first_in and gross_end else 0.0

    return {
        "status": "in" if signed_in else ("out" if sessions else "absent"),
        "signed_in_since": _iso(sessions[-1]["in"]) if signed_in else None,
        "unclosed": unclosed,
        "first_in": _iso(first_in),
        "last_out": _iso(last_out),
        "effective_seconds": int(effective),
        "gross_seconds": int(gross),
        "sessions": [
            {"in": _iso(s["in"]), "out": _iso(s["out"]),
             "in_source": s["in_source"], "out_source": s["out_source"]}
            for s in sessions
        ],
    }


def _punch_filter(tenant_id: int, users: list[User]):
    """
    Rows belonging to these people. By user_id, and also by finger for rows
    the offline scanner sync wrote without one.
    """
    ids = [u.id for u in users]
    fingers = [u.finger_id for u in users if u.finger_id is not None]
    cond = AttendanceLog.user_id.in_(ids)
    if fingers:
        cond = or_(cond, and_(AttendanceLog.user_id.is_(None), AttendanceLog.finger_id.in_(fingers)))
    return and_(AttendanceLog.tenant_id == tenant_id, cond)


async def punches_between(db, tenant_id: int, users: list[User],
                          start: dt.datetime, end: dt.datetime) -> dict[int, list]:
    """Punches in [start, end) grouped by user id."""
    if not users:
        return {}
    rows = (await db.execute(
        select(AttendanceLog)
        .where(_punch_filter(tenant_id, users),
               AttendanceLog.timestamp >= start, AttendanceLog.timestamp < end)
        .order_by(AttendanceLog.timestamp)
    )).scalars().all()
    by_finger = {u.finger_id: u.id for u in users if u.finger_id is not None}
    out: dict[int, list] = defaultdict(list)
    for r in rows:
        uid = r.user_id if r.user_id is not None else by_finger.get(r.finger_id)
        if uid is not None:
            out[uid].append(r)
    return out


async def today_for(db, user: User, now: dt.datetime | None = None) -> dict:
    now = now or now_utc()
    day = local_today(now)
    start, end = day_bounds(day)
    punches = (await punches_between(db, user.tenant_id, [user], start, end)).get(user.id, [])
    return {
        **summarise(punches, now, is_today=True),
        "date": day.isoformat(),
        "server_time": _iso(now),
        "timezone": settings.APP_TIMEZONE,
    }


async def history_for(db, user: User, days: int, now: dt.datetime | None = None) -> list[dict]:
    """The last `days` local days, newest first, today included."""
    now = now or now_utc()
    today = local_today(now)
    first = today - dt.timedelta(days=days - 1)
    start, _ = day_bounds(first)
    _, end = day_bounds(today)
    punches = (await punches_between(db, user.tenant_id, [user], start, end)).get(user.id, [])
    tz = zone()
    by_day: dict[dt.date, list] = defaultdict(list)
    for p in punches:
        by_day[aware(p.timestamp).astimezone(tz).date()].append(p)
    out = []
    for i in range(days):
        d = today - dt.timedelta(days=i)
        out.append({"date": d.isoformat(), **summarise(by_day.get(d, []), now, is_today=(d == today))})
    return out


async def team_for(db, tenant_id: int, dept_id: int | None, day: dt.date,
                   now: dt.datetime | None = None) -> dict:
    """
    Everyone in scope on one day: a department (Org Admin) or the whole
    organisation (dept_id None). Active employees and Org Admins — the
    people who clock in.
    """
    now = now or now_utc()
    q = select(User).where(
        User.tenant_id == tenant_id,
        User.is_active.is_(True),
        User.role.in_(("employee", "org_admin")),
    )
    if dept_id is not None:
        q = q.where(User.dept_id == dept_id)
    people = (await db.execute(q.order_by(User.name))).scalars().all()

    start, end = day_bounds(day)
    punches = await punches_between(db, tenant_id, list(people), start, end)
    is_today = day == local_today(now)
    rows = []
    for u in people:
        rows.append({
            "user_id": u.id, "name": u.name, "employee_code": u.employee_code,
            "role": u.role, "dept_id": u.dept_id,
            **summarise(punches.get(u.id, []), now, is_today=is_today),
        })
    counts = {
        "people": len(rows),
        "signed_in": sum(r["status"] == "in" for r in rows),
        "present": sum(r["status"] != "absent" for r in rows),
        "absent": sum(r["status"] == "absent" for r in rows),
    }
    return {"date": day.isoformat(), "timezone": settings.APP_TIMEZONE,
            "server_time": _iso(now), "counts": counts, "people": rows}
