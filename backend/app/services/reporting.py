"""
Work reporting: who can see whose reports and targets, and the small bits of
arithmetic the day-end reports and the Gantt timeline need.

Scope follows the same hierarchy as the rest of the app (oversight_service):

    Employee          their own reports and targets
    Department Admin  their department's employees
    Org Admin / HR    the organisation
    Tenant Admin      the organisation
    Super Admin       the organisation they are acting in

Pure helpers here; the database work is in the routes.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.models.domain import User
from app.services.oversight_service import _org, can_oversee

MONDAY = 0


# ─── dates ───────────────────────────────────────────────────────────────────

def week_start(day: dt.date) -> dt.date:
    """The Monday on or before `day`."""
    return day - dt.timedelta(days=day.weekday())


def week_end(day: dt.date) -> dt.date:
    return week_start(day) + dt.timedelta(days=6)


def period_bounds(period: str, day: dt.date) -> tuple[dt.date, dt.date]:
    if period == "week":
        return week_start(day), week_end(day)
    return day, day


# ─── scope ───────────────────────────────────────────────────────────────────

def can_view_person(viewer: User, target: User, tenant_id: int | None = None) -> bool:
    """May the viewer read this person's reports / targets? Themselves, or someone they oversee."""
    if viewer.id == target.id:
        return True
    return can_oversee(viewer, target, tenant_id)


def can_manage_target(viewer: User, target_owner_id: int | None, owner: User | None,
                      has_manage: bool, tenant_id: int | None = None) -> bool:
    """
    Change a target's details, milestones, dates.

    The owner keeps their own target's progress and milestones; an admin with
    target.manage keeps the targets of people they oversee (and department
    targets in their organisation).
    """
    if target_owner_id is not None and viewer.id == target_owner_id:
        return True
    if not has_manage:
        return False
    if owner is None:                               # department target
        return _org(viewer, tenant_id) is not None
    return can_oversee(viewer, owner, tenant_id)


# ─── numbers ─────────────────────────────────────────────────────────────────

def hours(value) -> float:
    return float(value) if value is not None else 0.0


def clamp_progress(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def sum_hours(lines) -> Decimal:
    total = Decimal("0")
    for line_hours in lines:
        if line_hours is not None:
            total += Decimal(str(line_hours))
    return total


# ─── Gantt status ────────────────────────────────────────────────────────────

def target_state(*, start: dt.date, end: dt.date, progress: int, status: str, today: dt.date) -> str:
    """
    A target's health, for the colour on the timeline:

      done        progress 100 or status done
      cancelled   status cancelled
      upcoming    not started yet
      overdue     past its end date and not complete
      at_risk     behind where the elapsed time says it should be (>20% gap)
      on_track    otherwise
    """
    if status == "cancelled":
        return "cancelled"
    if status == "done" or progress >= 100:
        return "done"
    if today < start:
        return "upcoming"
    if today > end:
        return "overdue"
    span = (end - start).days or 1
    elapsed = (today - start).days
    expected = min(100, round(elapsed / span * 100))
    return "at_risk" if progress + 20 < expected else "on_track"


def expected_progress(*, start: dt.date, end: dt.date, today: dt.date) -> int:
    if today <= start:
        return 0
    if today >= end:
        return 100
    span = (end - start).days or 1
    return min(100, round((today - start).days / span * 100))


# ─── day-end v2: assigned work, late reports, clock gap, reminders ──────────

ITEM_STATUS = ("not_started", "in_progress", "blocked", "done")
CLOSED = ("done", "cancelled")
PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
LATE_WINDOW_DAYS = 14            # how far back a missed day can still be filed


def item_visible_on(*, start: dt.date, status: str, completed_on: dt.date | None, day: dt.date) -> bool:
    """
    Is an assigned item on someone's list for `day`? From the day it was set
    until the day it was finished. Unfinished work therefore carries over.
    """
    if day < start or status == "cancelled":
        return False
    if status == "done":
        return completed_on is None or completed_on >= day
    return True


def carried_days(start: dt.date, day: dt.date) -> int:
    """Days an item has been on the list before `day` (0 on its first day)."""
    return max(0, (day - start).days)


def is_overdue(due: dt.date | None, status: str, day: dt.date) -> bool:
    return due is not None and status not in CLOSED and day > due


def item_progress(status: str, progress) -> int:
    """Done means 100%; otherwise whatever was reported, clamped."""
    if status == "done":
        return 100
    return clamp_progress(progress if progress is not None else 0)


def task_status_for(line_status: str, current: str) -> str | None:
    """
    The Task Manager status a report line implies, or None for no change.
    Task Manager has no "blocked"; a blocked task is still in progress.
    Never moves a task backwards out of review/done just because it was mentioned.
    """
    if line_status == "done":
        return None if current == "done" else "done"
    if line_status in ("in_progress", "blocked"):
        return "in_progress" if current == "todo" else None
    return None


def can_file_for(day: dt.date, today: dt.date) -> str | None:
    """None if a report may be written for `day`, else the reason it may not."""
    if day > today:
        return "You cannot report for a future day."
    if (today - day).days > LATE_WINDOW_DAYS:
        return f"Reports can be filed up to {LATE_WINDOW_DAYS} days late."
    return None


def hours_gap(reported: float, clock_seconds: int | None) -> dict | None:
    """
    Compare reported hours with signed-in time. Flag a gap of more than an
    hour and a half, and more than a quarter of the signed-in time — small
    differences are breaks and rounding, not a problem.
    """
    if not clock_seconds:
        return None
    clock_h = round(clock_seconds / 3600, 2)
    diff = round(reported - clock_h, 2)
    flagged = abs(diff) > 1.5 and abs(diff) > clock_h * 0.25
    return {"clock_hours": clock_h, "reported_hours": round(reported, 2), "difference": diff, "flagged": flagged}


def parse_clock(value: str | None, default: dt.time) -> dt.time:
    try:
        return dt.time.fromisoformat(value) if value else default
    except ValueError:
        return default


def reminder_due(now_local: dt.datetime, office_end: dt.time, working_days: str | None,
                 lead_minutes: int = 30) -> bool:
    """
    Is it time to remind people about today's report? From `lead_minutes`
    before the end of the office day, on working days only. working_days is
    "1,2,3,4,5" with Monday = 1.
    """
    try:
        days = {int(x) for x in (working_days or "1,2,3,4,5").split(",") if x.strip()}
    except ValueError:
        days = {1, 2, 3, 4, 5}
    if now_local.isoweekday() not in days:
        return False
    end = dt.datetime.combine(now_local.date(), office_end, tzinfo=now_local.tzinfo)
    return now_local >= end - dt.timedelta(minutes=lead_minutes)


def sort_items(items: list[dict]) -> list[dict]:
    """Blocked and overdue first, then by priority, then by due date."""
    far = dt.date.max.isoformat()
    return sorted(items, key=lambda i: (
        i["status"] in CLOSED,
        not (i["status"] == "blocked" or i.get("overdue")),
        PRIORITY_RANK.get(i.get("priority") or "medium", 2),
        i.get("due_date") or far,
        i["title"].lower(),
    ))
