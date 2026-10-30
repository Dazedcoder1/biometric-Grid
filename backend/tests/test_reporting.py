"""Reporting helpers: week bounds, scope, and the Gantt health of a target."""
from __future__ import annotations

import datetime as dt

import pytest

from app.services import reporting as R


class U:
    def __init__(self, id, role, tenant_id=1, dept_id=None):
        self.id, self.role, self.tenant_id, self.dept_id = id, role, tenant_id, dept_id


SA = U(1, "super_admin", tenant_id=None)
OA = U(2, "tenant_admin", 1)
DA = U(3, "org_admin", 1, dept_id=10)
EMP = U(4, "employee", 1, dept_id=10)
EMP_IT = U(5, "employee", 1, dept_id=11)
OTHER = U(6, "employee", 2, dept_id=20)


def test_week_bounds():
    # 2026-10-30 is a Friday.
    assert R.week_start(dt.date(2026, 10, 30)) == dt.date(2026, 10, 26)   # Monday
    assert R.week_end(dt.date(2026, 10, 30)) == dt.date(2026, 11, 1)      # Sunday
    assert R.period_bounds("day", dt.date(2026, 10, 30)) == (dt.date(2026, 10, 30), dt.date(2026, 10, 30))
    assert R.period_bounds("week", dt.date(2026, 10, 30)) == (dt.date(2026, 10, 26), dt.date(2026, 11, 1))


@pytest.mark.parametrize("viewer,target,ok", [
    (EMP, EMP, True),                      # yourself
    (DA, EMP, True), (DA, EMP_IT, False),  # department only
    (OA, EMP_IT, True), (OA, OTHER, False),
    (SA, OTHER, True),                     # super admin acting in org 1 cannot see org 2's person via tenant scope
    (EMP, EMP_IT, False),
])
def test_can_view_person(viewer, target, ok):
    # Super Admin needs the acting tenant; pass the target's tenant for SA cases.
    tenant = target.tenant_id if viewer.role == "super_admin" else None
    assert R.can_view_person(viewer, target, tenant) is ok


def test_manage_target_owner_or_admin():
    # Owner always manages their own.
    assert R.can_manage_target(EMP, EMP.id, EMP, has_manage=False)
    # A non-owner needs manage and scope.
    assert R.can_manage_target(DA, EMP.id, EMP, has_manage=True)
    assert not R.can_manage_target(DA, EMP_IT.id, EMP_IT, has_manage=True)
    assert not R.can_manage_target(DA, EMP.id, EMP, has_manage=False)
    # Department target: an org admin with manage can.
    assert R.can_manage_target(OA, None, None, has_manage=True)


def test_clamp_and_hours():
    assert R.clamp_progress(150) == 100 and R.clamp_progress(-5) == 0
    assert R.clamp_progress("40") == 40 and R.clamp_progress("x") == 0
    assert float(R.sum_hours([1.5, 2, None, "0.5"])) == 4.0


D = dt.date


@pytest.mark.parametrize("start,end,progress,status,today,state", [
    (D(2026, 1, 1), D(2026, 7, 1), 100, "active", D(2026, 3, 1), "done"),
    (D(2026, 1, 1), D(2026, 7, 1), 30, "cancelled", D(2026, 3, 1), "cancelled"),
    (D(2026, 6, 1), D(2026, 12, 1), 0, "active", D(2026, 3, 1), "upcoming"),
    (D(2026, 1, 1), D(2026, 2, 1), 40, "active", D(2026, 3, 1), "overdue"),
    # Half-way through, only 10% done → at risk (expected ~50%).
    (D(2026, 1, 1), D(2026, 3, 1), 10, "active", D(2026, 2, 1), "at_risk"),
    # Half-way through, 60% done → on track.
    (D(2026, 1, 1), D(2026, 3, 1), 60, "active", D(2026, 2, 1), "on_track"),
])
def test_target_state(start, end, progress, status, today, state):
    assert R.target_state(start=start, end=end, progress=progress, status=status, today=today) == state


def test_expected_progress():
    assert R.expected_progress(start=D(2026, 1, 1), end=D(2026, 3, 1), today=D(2025, 12, 1)) == 0
    assert R.expected_progress(start=D(2026, 1, 1), end=D(2026, 3, 1), today=D(2026, 4, 1)) == 100
    assert 45 <= R.expected_progress(start=D(2026, 1, 1), end=D(2026, 3, 1), today=D(2026, 2, 1)) <= 55


# ─── day-end v2 ──────────────────────────────────────────────────────────────

DAY = dt.date(2026, 10, 28)


@pytest.mark.parametrize("start,status,completed,day,expected", [
    (DAY, "not_started", None, DAY, True),
    (DAY, "in_progress", None, DAY + dt.timedelta(days=5), True),      # carries over
    (DAY, "in_progress", None, DAY - dt.timedelta(days=1), False),     # not yet assigned
    (DAY, "cancelled", None, DAY, False),
    (DAY, "done", DAY + dt.timedelta(days=2), DAY + dt.timedelta(days=2), True),   # visible on the day it finished
    (DAY, "done", DAY + dt.timedelta(days=2), DAY + dt.timedelta(days=3), False),  # gone after
    (DAY, "done", DAY + dt.timedelta(days=2), DAY + dt.timedelta(days=1), True),   # history still shows it
])
def test_item_visible_on(start, status, completed, day, expected):
    assert R.item_visible_on(start=start, status=status, completed_on=completed, day=day) is expected


def test_carried_and_overdue():
    assert R.carried_days(DAY, DAY) == 0
    assert R.carried_days(DAY, DAY + dt.timedelta(days=3)) == 3
    assert R.is_overdue(DAY, "in_progress", DAY + dt.timedelta(days=1)) is True
    assert R.is_overdue(DAY, "in_progress", DAY) is False
    assert R.is_overdue(DAY, "done", DAY + dt.timedelta(days=9)) is False
    assert R.is_overdue(None, "in_progress", DAY) is False


def test_item_progress():
    assert R.item_progress("done", 10) == 100
    assert R.item_progress("in_progress", 140) == 100
    assert R.item_progress("in_progress", None) == 0
    assert R.item_progress("blocked", 35) == 35


@pytest.mark.parametrize("line,current,expected", [
    ("done", "todo", "done"), ("done", "in_review", "done"), ("done", "done", None),
    ("in_progress", "todo", "in_progress"), ("blocked", "todo", "in_progress"),
    ("in_progress", "in_review", None), ("not_started", "in_progress", None),
])
def test_task_status_for(line, current, expected):
    assert R.task_status_for(line, current) == expected


def test_can_file_for():
    today = DAY
    assert R.can_file_for(today, today) is None
    assert R.can_file_for(today - dt.timedelta(days=R.LATE_WINDOW_DAYS), today) is None
    assert "late" in R.can_file_for(today - dt.timedelta(days=R.LATE_WINDOW_DAYS + 1), today)
    assert "future" in R.can_file_for(today + dt.timedelta(days=1), today)


def test_hours_gap():
    assert R.hours_gap(8, None) is None
    small = R.hours_gap(8, int(8.5 * 3600))
    assert small["flagged"] is False and small["clock_hours"] == 8.5
    big = R.hours_gap(3, 9 * 3600)
    assert big["flagged"] is True and big["difference"] == -6


def test_reminder_due():
    tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
    wed_1700 = dt.datetime(2026, 10, 28, 17, 0, tzinfo=tz)
    wed_1735 = dt.datetime(2026, 10, 28, 17, 35, tzinfo=tz)
    sat_1900 = dt.datetime(2026, 10, 31, 19, 0, tzinfo=tz)
    assert R.reminder_due(wed_1700, dt.time(18, 0), "1,2,3,4,5") is False
    assert R.reminder_due(wed_1735, dt.time(18, 0), "1,2,3,4,5") is True
    assert R.reminder_due(sat_1900, dt.time(18, 0), "1,2,3,4,5") is False
    assert R.reminder_due(sat_1900, dt.time(18, 0), "1,2,3,4,5,6") is True
    assert R.reminder_due(wed_1735, dt.time(18, 0), "garbage") is True


def test_parse_clock():
    assert R.parse_clock("17:30:00", dt.time(18)) == dt.time(17, 30)
    assert R.parse_clock("nope", dt.time(18)) == dt.time(18)
    assert R.parse_clock(None, dt.time(18)) == dt.time(18)


def test_sort_items_puts_blocked_and_overdue_first():
    # Items needing attention lead, ordered among themselves by priority.
    items = [
        {"title": "low later", "status": "not_started", "priority": "low", "due_date": None},
        {"title": "urgent", "status": "in_progress", "priority": "urgent", "due_date": "2026-11-05"},
        {"title": "blocked", "status": "blocked", "priority": "low", "due_date": None},
        {"title": "overdue", "status": "in_progress", "priority": "medium", "due_date": "2026-10-01", "overdue": True},
        {"title": "finished", "status": "done", "priority": "urgent", "due_date": None},
    ]
    assert [i["title"] for i in R.sort_items(items)] == ["overdue", "blocked", "urgent", "low later", "finished"]
