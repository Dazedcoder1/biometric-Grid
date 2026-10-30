"""
Day-end reports and targets — /api/reporting.

Self-service (anyone in an organisation)
    /me/day?date=                 everything My Day needs for one day: the work assigned to
                                  me (Reporting items and Task Manager tasks), my report,
                                  my signed-in time, and the plan I wrote the day before
    /me/reports?days=             my recent reports
    /me/reports/{date}            GET / PUT (draft: summary, blockers, plan, lines)
    /me/reports/{date}/submit     submit; updates the linked items and tasks, and alerts
                                  whoever assigned anything I marked blocked
    /me/targets                   my targets, with milestones and Gantt health
    /me/targets/{id}/progress     update progress (owner)

Admin
    /people                       who I oversee (report.view)
    /departments                  departments in the organisation (target.manage)
    /team/reports?date=           my team's reports for a day, who is missing, and each
                                  person's open / blocked / overdue work (report.view)
    /team/items?user_id=&date=    one person's assigned work (report.view)
    /reports/{id}                 one report (report.view)
    /reports/{id}/review          add a review note (report.manage)
    /reports/{id}/reopen          send a submitted report back with a comment (report.manage)
    /assignments                  POST assign work (report.manage)
    /assignments/{id}             PATCH edit / cancel, DELETE (report.manage)
    /targets                      GET all targets in scope for the Gantt (target.view)
                                  POST create a target with milestones (target.manage)
    /targets/{id}                 GET / PATCH / DELETE
    /targets/{id}/progress        POST update progress (owner or target.manage)
    /targets/{id}/milestones      POST add; /{mid} PATCH, DELETE

Everything is scoped by the oversight hierarchy and checked on the server.
A person outside the caller's scope gets the same 404 as one who does not exist.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import (
    SecurityContext,
    get_security_context,
    require_organisation,
    require_permission,
)
from app.core import audit
from app.db.session import get_db
from app.models.domain import (
    DailyReport,
    DailyReportLine,
    Department,
    Settings,
    Target,
    TargetMilestone,
    TargetUpdate,
    Task,
    User,
    WorkAssignment,
)
from app.services import clock_service, notification_service
from app.services import reporting as R
from app.services import task_service as task_svc
from app.services.oversight_service import _scope_query

logger = logging.getLogger(__name__)
router = APIRouter()

ItemStatus = Literal["not_started", "in_progress", "blocked", "done"]
Priority = Literal["low", "medium", "high", "urgent"]
# Task Manager's statuses, seen through the day-end report's eyes.
TASK_TO_ITEM = {"todo": "not_started", "in_progress": "in_progress", "in_review": "in_progress", "done": "done"}


def _tid(ctx: SecurityContext) -> int:
    return require_organisation(ctx)


async def _overseen(db, ctx: SecurityContext, tid: int) -> list[User]:
    q = _scope_query(ctx.user, tid)
    if q is None:
        return []
    return list((await db.execute(q.order_by(User.name))).scalars().all())


async def _in_scope_person(db, ctx: SecurityContext, tid: int, user_id: int) -> User:
    u = (await db.execute(select(User).where(User.id == user_id, User.tenant_id == tid))).scalars().first()
    if not u or not R.can_view_person(ctx.user, u, tid):
        raise HTTPException(404, "Person not found.")
    return u


async def _names(db, ids) -> dict[int, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {u.id: u.name for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()}


def _parse_date(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(422, "Date must be YYYY-MM-DD.") from None


def _iso(d) -> str | None:
    return d.isoformat() if d else None


async def _settings(db, tid: int) -> Settings | None:
    return (await db.execute(select(Settings).where(Settings.tenant_id == tid))).scalars().first()


async def _managers_of(db, tid: int, user: User) -> list[int]:
    """Who hears about a person's blockers: their Department Admin, else the Organisation Admins."""
    ids: list[int] = []
    if user.role == "employee" and user.dept_id:
        ids = [i for (i,) in (await db.execute(select(User.id).where(
            User.tenant_id == tid, User.dept_id == user.dept_id, User.role == "org_admin",
            User.is_active.is_(True)))).all()]
    if not ids:
        ids = [i for (i,) in (await db.execute(select(User.id).where(
            User.tenant_id == tid, User.role == "tenant_admin", User.is_active.is_(True)))).all()]
    return [i for i in ids if i != user.id]


# ─── serialising ─────────────────────────────────────────────────────────────

async def _lines_of(db, report_ids: list[int]) -> dict[int, list[DailyReportLine]]:
    if not report_ids:
        return {}
    rows = (await db.execute(select(DailyReportLine).where(
        DailyReportLine.report_id.in_(report_ids)).order_by(DailyReportLine.sort_order, DailyReportLine.id))).scalars().all()
    out: dict[int, list] = {}
    for r in rows:
        out.setdefault(r.report_id, []).append(r)
    return out


def _line_view(line: DailyReportLine) -> dict:
    return {"id": line.id, "what": line.what, "hours": R.hours(line.hours), "status": line.status,
            "target_id": line.target_id, "assignment_id": line.assignment_id, "task_id": line.task_id,
            "progress": line.progress, "note": line.note}


def _report_view(r: DailyReport, lines: list[DailyReportLine], names: dict[int, str]) -> dict:
    return {
        "id": r.id, "user_id": r.user_id, "employee": names.get(r.user_id),
        "date": r.report_date.isoformat(), "summary": r.summary, "status": r.status,
        "blockers": r.blockers, "tomorrow_plan": r.tomorrow_plan,
        "hours_total": R.hours(r.hours_total), "submitted_at": r.submitted_at,
        "is_late": bool(r.is_late), "clock_seconds": r.clock_seconds,
        "reviewed_by": names.get(r.reviewed_by), "reviewed_at": r.reviewed_at, "review_note": r.review_note,
        "reopened_by": names.get(r.reopened_by), "reopened_at": r.reopened_at, "reopen_note": r.reopen_note,
        "lines": [_line_view(x) for x in lines],
    }


async def _report_names(db, reports: list[DailyReport]) -> dict[int, str]:
    ids = []
    for r in reports:
        ids += [r.user_id, r.reviewed_by, r.reopened_by]
    return await _names(db, ids)


# ─── assigned work: Reporting items + Task Manager tasks ─────────────────────

def _task_due(t: Task) -> dt.date | None:
    d = t.due_date
    if d is None:
        return None
    return d.date() if isinstance(d, dt.datetime) else d


def _assignment_item(a: WorkAssignment, day: dt.date, names: dict[int, str], reported: dict | None = None) -> dict:
    return {
        "key": f"a:{a.id}", "kind": "assignment", "id": a.id, "user_id": a.user_id,
        "title": a.title, "details": a.details, "priority": a.priority or "medium",
        "due_date": _iso(a.due_date), "status": a.status, "progress": a.progress or 0,
        "assigned_by": names.get(a.assigned_by), "since": a.start_date.isoformat(),
        "carried_days": R.carried_days(a.start_date, day),
        "overdue": R.is_overdue(a.due_date, a.status, day),
        "target_id": a.target_id, "url": None, "reported": reported,
    }


def _task_item(t: Task, day: dt.date, names: dict[int, str], reported: dict | None = None) -> dict:
    status = TASK_TO_ITEM.get(t.status, "not_started")
    due = _task_due(t)
    since = t.created_at.date() if t.created_at else day
    return {
        "key": f"t:{t.id}", "kind": "task", "id": t.id, "user_id": t.assigned_to,
        "title": t.title, "details": t.description, "priority": t.priority or "medium",
        "due_date": _iso(due), "status": status, "task_status": t.status,
        "progress": 100 if status == "done" else 0,
        "assigned_by": names.get(t.created_by), "since": since.isoformat(),
        "carried_days": R.carried_days(since, day), "overdue": R.is_overdue(due, status, day),
        "target_id": None, "url": t.github_url, "reported": reported,
    }


async def _open_assignments(db, user_ids: list[int], day: dt.date) -> list[WorkAssignment]:
    rows = (await db.execute(select(WorkAssignment).where(
        WorkAssignment.user_id.in_(user_ids or [0]),
        WorkAssignment.start_date <= day,
        WorkAssignment.status != "cancelled",
        or_(WorkAssignment.status != "done", WorkAssignment.completed_on.is_(None),
            WorkAssignment.completed_on >= day),
    ))).scalars().all()
    return [a for a in rows if R.item_visible_on(start=a.start_date, status=a.status,
                                                  completed_on=a.completed_on, day=day)]


async def _open_tasks(db, tid: int, user_ids: list[int], keep_ids=()) -> list[Task]:
    conds = [Task.status != "done"]
    if keep_ids:
        conds.append(Task.id.in_(list(keep_ids)))
    return list((await db.execute(select(Task).where(
        Task.tenant_id == tid, Task.assigned_to.in_(user_ids or [0]), or_(*conds)))).scalars().all())


async def _items_for(db, tid: int, user: User, day: dt.date, lines: list[DailyReportLine]) -> list[dict]:
    by_a = {x.assignment_id: x for x in lines if x.assignment_id}
    by_t = {x.task_id: x for x in lines if x.task_id}
    assigns = await _open_assignments(db, [user.id], day)
    # Anything this day's report talks about stays visible, even once closed.
    missing = set(by_a) - {a.id for a in assigns}
    if missing:
        assigns += list((await db.execute(select(WorkAssignment).where(
            WorkAssignment.id.in_(missing), WorkAssignment.user_id == user.id))).scalars().all())
    tasks = await _open_tasks(db, tid, [user.id], by_t.keys())
    names = await _names(db, [a.assigned_by for a in assigns] + [t.created_by for t in tasks])
    items = [_assignment_item(a, day, names, _line_view(by_a[a.id]) if a.id in by_a else None) for a in assigns]
    items += [_task_item(t, day, names, _line_view(by_t[t.id]) if t.id in by_t else None) for t in tasks]
    return R.sort_items(items)


async def _clock_on(db, tid: int, user: User, day: dt.date) -> dict:
    start, end = clock_service.day_bounds(day)
    punches = (await clock_service.punches_between(db, tid, [user], start, end)).get(user.id, [])
    s = clock_service.summarise(punches, clock_service.now_utc(), is_today=(day == clock_service.local_today()))
    return {"status": s["status"], "effective_seconds": s["effective_seconds"], "first_in": s["first_in"],
            "last_out": s["last_out"], "unclosed": s["unclosed"]}


# ─── self-service: My Day ────────────────────────────────────────────────────

class LineIn(BaseModel):
    what: str = Field(..., min_length=1, max_length=500)
    hours: float | None = Field(None, ge=0, le=24)
    status: ItemStatus = "done"
    target_id: int | None = None
    assignment_id: int | None = None
    task_id: int | None = None
    progress: int | None = Field(None, ge=0, le=100)
    note: str | None = Field(None, max_length=500)


class ReportIn(BaseModel):
    summary: str | None = Field(None, max_length=5000)
    blockers: str | None = Field(None, max_length=3000)
    tomorrow_plan: str | None = Field(None, max_length=3000)
    lines: list[LineIn] = Field(default_factory=list, max_length=40)


async def _get_or_make_report(db, tid: int, user_id: int, day: dt.date, create: bool) -> DailyReport | None:
    r = (await db.execute(select(DailyReport).where(
        DailyReport.user_id == user_id, DailyReport.report_date == day))).scalars().first()
    if r is None and create:
        r = DailyReport(tenant_id=tid, user_id=user_id, report_date=day, status="draft")
        db.add(r)
        await db.flush()
    return r


async def _check_links(db, tid: int, user: User, lines: list[LineIn]) -> None:
    """Every linked item and task must be the caller's own, and appear once."""
    a_ids = [x.assignment_id for x in lines if x.assignment_id]
    t_ids = [x.task_id for x in lines if x.task_id]
    if any(x.assignment_id and x.task_id for x in lines):
        raise HTTPException(422, "A line reports on one item, not two.")
    if len(set(a_ids)) != len(a_ids) or len(set(t_ids)) != len(t_ids):
        raise HTTPException(422, "Each assigned item can appear only once in a report.")
    if a_ids:
        n = (await db.execute(select(func.count(WorkAssignment.id)).where(
            WorkAssignment.id.in_(a_ids), WorkAssignment.user_id == user.id,
            WorkAssignment.tenant_id == tid))).scalar() or 0
        if n != len(a_ids):
            raise HTTPException(422, "One of those assigned items is not yours.")
    if t_ids:
        n = (await db.execute(select(func.count(Task.id)).where(
            Task.id.in_(t_ids), Task.assigned_to == user.id, Task.tenant_id == tid))).scalar() or 0
        if n != len(t_ids):
            raise HTTPException(422, "One of those tasks is not assigned to you.")


async def _write_lines(db, report: DailyReport, lines: list[LineIn]) -> None:
    for old in (await db.execute(select(DailyReportLine).where(DailyReportLine.report_id == report.id))).scalars().all():
        await db.delete(old)
    await db.flush()
    for i, line in enumerate(lines):
        progress = None
        if line.assignment_id or line.task_id or line.progress is not None:
            progress = R.item_progress(line.status, line.progress)
        db.add(DailyReportLine(
            report_id=report.id, what=line.what.strip(), hours=line.hours, status=line.status,
            target_id=line.target_id, assignment_id=line.assignment_id, task_id=line.task_id,
            progress=progress, note=(line.note or "").strip() or None, sort_order=i))
    report.hours_total = R.sum_hours([line.hours for line in lines])


def _working_days(cfg: Settings | None) -> set[int]:
    try:
        return {int(x) for x in ((cfg.working_days if cfg else None) or "1,2,3,4,5").split(",") if x.strip()}
    except ValueError:
        return {1, 2, 3, 4, 5}


@router.get("/me/day")
async def my_day(date: str | None = None, ctx: SecurityContext = Depends(get_security_context),
                 db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    me = ctx.user
    today = clock_service.local_today()
    day = _parse_date(date) if date else today
    if day > today:
        raise HTTPException(422, "You cannot open a future day.")

    r = await _get_or_make_report(db, tid, me.id, day, create=False)
    lines = (await _lines_of(db, [r.id])).get(r.id, []) if r else []
    items = await _items_for(db, tid, me, day, lines)
    clock = await _clock_on(db, tid, me, day)
    cfg = await _settings(db, tid)

    prev = (await db.execute(select(DailyReport).where(
        DailyReport.user_id == me.id, DailyReport.report_date < day,
        DailyReport.report_date >= day - dt.timedelta(days=7),
        DailyReport.tomorrow_plan.is_not(None)).order_by(DailyReport.report_date.desc()))).scalars().first()

    # The last seven days, for the date strip: what was filed, and what is missing.
    week_days = [today - dt.timedelta(days=i) for i in range(6, -1, -1)]
    recent = {x.report_date: x for x in (await db.execute(select(DailyReport).where(
        DailyReport.user_id == me.id, DailyReport.report_date >= week_days[0]))).scalars().all()}
    workdays = _working_days(cfg)
    week = [{"date": d.isoformat(), "working": d.isoweekday() in workdays,
             "state": recent[d].status if d in recent else "missing",
             "late": bool(recent[d].is_late) if d in recent else False} for d in week_days]

    blocked_reason = R.can_file_for(day, today)
    reported = R.hours(r.hours_total) if r else 0.0
    return {
        "date": day.isoformat(), "today": today.isoformat(), "is_today": day == today,
        "late": day < today,
        "editable": blocked_reason is None and (r is None or r.status == "draft"),
        "locked_reason": blocked_reason,
        "report": _report_view(r, lines, await _report_names(db, [r])) if r else None,
        "items": items,
        "other_lines": [_line_view(x) for x in lines if not (x.assignment_id or x.task_id)],
        "clock": clock,
        "hours_gap": R.hours_gap(reported, clock["effective_seconds"]) if reported else None,
        "min_working_hours": float(cfg.min_working_hours) if cfg and cfg.min_working_hours else 9.0,
        "plan_from_previous": ({"date": prev.report_date.isoformat(), "text": prev.tomorrow_plan} if prev else None),
        "week": week,
    }


@router.get("/me/reports")
async def my_reports(days: int = Query(30, ge=1, le=120),
                     ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    _tid(ctx)
    since = clock_service.local_today() - dt.timedelta(days=days)
    rows = (await db.execute(select(DailyReport).where(
        DailyReport.user_id == ctx.user.id, DailyReport.report_date >= since)
        .order_by(DailyReport.report_date.desc()))).scalars().all()
    lines = await _lines_of(db, [r.id for r in rows])
    names = await _report_names(db, list(rows))
    return [_report_view(r, lines.get(r.id, []), names) for r in rows]


@router.put("/me/reports/{date}")
async def save_my_report(date: str, data: ReportIn,
                         ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    day = _parse_date(date)
    reason = R.can_file_for(day, clock_service.local_today())
    if reason:
        raise HTTPException(422, reason)
    await _check_links(db, tid, ctx.user, data.lines)
    r = await _get_or_make_report(db, tid, ctx.user.id, day, create=True)
    if r.status == "submitted":
        raise HTTPException(409, "This report is submitted. Ask your manager to reopen it if it needs changing.")
    r.summary = (data.summary or "").strip() or None
    r.blockers = (data.blockers or "").strip() or None
    r.tomorrow_plan = (data.tomorrow_plan or "").strip() or None
    await _write_lines(db, r, data.lines)
    await db.commit()
    lines = (await _lines_of(db, [r.id])).get(r.id, [])
    return _report_view(r, lines, await _report_names(db, [r]))


@router.get("/me/reports/{date}")
async def get_my_report(date: str, ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    _tid(ctx)
    r = await _get_or_make_report(db, ctx.user.tenant_id, ctx.user.id, _parse_date(date), create=False)
    if not r:
        return None
    lines = (await _lines_of(db, [r.id])).get(r.id, [])
    return _report_view(r, lines, await _report_names(db, [r]))


@router.post("/me/reports/{date}/submit")
async def submit_my_report(date: str, ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    me = ctx.user
    day = _parse_date(date)
    today = clock_service.local_today()
    r = await _get_or_make_report(db, tid, me.id, day, create=False)
    if not r:
        raise HTTPException(404, "Nothing to submit — write your report first.")
    lines = (await _lines_of(db, [r.id])).get(r.id, [])
    if r.status == "submitted":
        return _report_view(r, lines, await _report_names(db, [r]))
    reason = R.can_file_for(day, today)
    if reason:
        raise HTTPException(422, reason)
    if not (r.summary or lines):
        raise HTTPException(422, "Add a summary or at least one line before submitting.")
    unexplained = [x.what for x in lines if x.status == "blocked" and not x.note]
    if unexplained:
        raise HTTPException(422, f"Say what is blocking “{unexplained[0]}” before submitting.")

    r.status = "submitted"
    r.submitted_at = clock_service.now_utc()
    r.is_late = day < today
    r.clock_seconds = (await _clock_on(db, tid, me, day))["effective_seconds"] or None

    # Carry what the report says back to the work itself.
    changed_tasks: list[Task] = []
    alerted: set[int] = set()
    for line in lines:
        assigner, title = None, line.what
        if line.assignment_id:
            a = (await db.execute(select(WorkAssignment).where(
                WorkAssignment.id == line.assignment_id, WorkAssignment.user_id == me.id))).scalars().first()
            if a and a.status != "cancelled":
                a.status = line.status
                a.progress = R.item_progress(line.status, line.progress)
                a.completed_on = day if line.status == "done" else None
                assigner, title = a.assigned_by, a.title
        if line.task_id:
            t = (await db.execute(select(Task).where(
                Task.id == line.task_id, Task.assigned_to == me.id, Task.tenant_id == tid))).scalars().first()
            if t:
                new = R.task_status_for(line.status, t.status)
                if new:
                    before = t.status
                    await task_svc.apply_status_change(t, new)
                    changed_tasks.append(t)
                    await audit.record(db, action="task.status_changed", target_type="task", target_id=t.id,
                                       details={"title": t.title, "from": before, "to": new,
                                                "via": "day-end report"}, **ctx.audit_kwargs())
                assigner, title = t.created_by, t.title
        if line.status == "blocked" and assigner and assigner != me.id:
            alerted.add(assigner)
            await notification_service.notify_single_user(
                db, tenant_id=tid, actor_id=me.id, recipient_id=assigner, event_type="work_blocked",
                title=f"{me.name} is blocked: {title}"[:200], message=line.note or "Marked blocked in the day-end report.",
                entity_type="daily_report", entity_id=r.id, entity_name=day.isoformat())
    if r.blockers:
        for m in await _managers_of(db, tid, me):
            if m in alerted:
                continue
            await notification_service.notify_single_user(
                db, tenant_id=tid, actor_id=me.id, recipient_id=m, event_type="report_blockers",
                title=f"{me.name} reported blockers ({day.isoformat()})", message=r.blockers[:500],
                entity_type="daily_report", entity_id=r.id, entity_name=day.isoformat())

    await audit.record(db, action="report.submitted", target_type="daily_report", target_id=r.id,
                       details={"date": day.isoformat(), "hours": R.hours(r.hours_total), "late": r.is_late,
                                "blocked": sum(1 for x in lines if x.status == "blocked")},
                       **ctx.audit_kwargs())
    await db.commit()

    # GitHub-mirrored tasks: closing the issue is best-effort and never undoes the report.
    for t in changed_tasks:
        try:
            await task_svc.push_task_update(db, t, {"status"})
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub push for task %s failed: %s", t.id, exc)
    return _report_view(r, lines, await _report_names(db, [r]))


# ─── admin: people, team reports, review, reopen ─────────────────────────────

@router.get("/people")
async def overseen_people(ctx: SecurityContext = Depends(require_permission("report.view")),
                          db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    depts = {d.department_id: d.department_name for d in (await db.execute(
        select(Department).where(Department.tenant_id == tid))).scalars().all()}
    people = await _overseen(db, ctx, tid)
    return [{"id": u.id, "name": u.name, "employee_code": u.employee_code, "role": u.role,
             "dept_id": u.dept_id, "department": depts.get(u.dept_id)} for u in people]


@router.get("/departments")
async def departments(ctx: SecurityContext = Depends(require_permission("target.manage")),
                      db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    rows = (await db.execute(select(Department).where(
        Department.tenant_id == tid, Department.is_active.is_(True)).order_by(Department.department_name))).scalars().all()
    # An Org Admin's targets are limited to their own department.
    if ctx.user.role == "org_admin" and not ctx.permissions.grants_all:
        rows = [d for d in rows if d.department_id == ctx.user.dept_id]
    return [{"id": d.department_id, "name": d.department_name} for d in rows]


@router.get("/team/reports")
async def team_reports(date: str | None = None,
                       ctx: SecurityContext = Depends(require_permission("report.view")),
                       db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    day = _parse_date(date) if date else clock_service.local_today()
    people = await _overseen(db, ctx, tid)
    ids = [u.id for u in people]
    reports = (await db.execute(select(DailyReport).where(
        DailyReport.user_id.in_(ids or [0]), DailyReport.report_date == day))).scalars().all()
    lines = await _lines_of(db, [r.id for r in reports])
    names = await _report_names(db, list(reports))
    names.update({u.id: u.name for u in people})
    by_user = {r.user_id: r for r in reports}
    depts = {d.department_id: d.department_name for d in (await db.execute(
        select(Department).where(Department.tenant_id == tid))).scalars().all()}

    # Open work per person: Reporting items and Task Manager tasks.
    work: dict[int, dict] = {u.id: {"open": 0, "blocked": 0, "overdue": 0} for u in people}
    for a in await _open_assignments(db, ids, day):
        if a.status != "done":
            w = work[a.user_id]
            w["open"] += 1
            w["blocked"] += a.status == "blocked"
            w["overdue"] += R.is_overdue(a.due_date, a.status, day)
    for t in await _open_tasks(db, tid, ids):
        w = work.get(t.assigned_to)
        if w is not None:
            w["open"] += 1
            w["overdue"] += R.is_overdue(_task_due(t), TASK_TO_ITEM.get(t.status, "not_started"), day)

    rows = []
    for u in people:
        r = by_user.get(u.id)
        view = _report_view(r, lines.get(r.id, []), names) if r else None
        rows.append({
            "user_id": u.id, "name": u.name, "employee_code": u.employee_code,
            "department": depts.get(u.dept_id),
            "report": view,
            "state": r.status if r else "missing",
            "work": work[u.id],
            "has_blockers": bool(view and (view["blockers"] or any(x["status"] == "blocked" for x in view["lines"]))),
        })
    counts = {
        "people": len(rows),
        "submitted": sum(1 for x in rows if x["state"] == "submitted"),
        "draft": sum(1 for x in rows if x["state"] == "draft"),
        "missing": sum(1 for x in rows if x["state"] == "missing"),
        "reviewed": sum(1 for x in rows if x["report"] and x["report"]["reviewed_at"]),
        "blocked": sum(1 for x in rows if x["has_blockers"]),
        "late": sum(1 for x in rows if x["report"] and x["report"]["is_late"]),
    }
    return {"date": day.isoformat(), "counts": counts, "people": rows}


@router.get("/team/items")
async def team_items(user_id: int, date: str | None = None,
                     ctx: SecurityContext = Depends(require_permission("report.view")),
                     db: AsyncSession = Depends(get_db)):
    """One person's assigned work, as they see it in My Day."""
    tid = _tid(ctx)
    person = await _in_scope_person(db, ctx, tid, user_id)
    day = _parse_date(date) if date else clock_service.local_today()
    r = await _get_or_make_report(db, tid, person.id, day, create=False)
    lines = (await _lines_of(db, [r.id])).get(r.id, []) if r else []
    return await _items_for(db, tid, person, day, lines)


@router.get("/reports/{report_id}")
async def get_report(report_id: int, ctx: SecurityContext = Depends(require_permission("report.view")),
                     db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    r = (await db.execute(select(DailyReport).where(DailyReport.id == report_id, DailyReport.tenant_id == tid))).scalars().first()
    if not r:
        raise HTTPException(404, "Report not found.")
    await _in_scope_person(db, ctx, tid, r.user_id)
    lines = (await _lines_of(db, [r.id])).get(r.id, [])
    return _report_view(r, lines, await _report_names(db, [r]))


class ReviewIn(BaseModel):
    note: str | None = Field(None, max_length=500)


async def _team_report(db, ctx, tid: int, report_id: int) -> tuple[DailyReport, User]:
    r = (await db.execute(select(DailyReport).where(DailyReport.id == report_id, DailyReport.tenant_id == tid))).scalars().first()
    if not r:
        raise HTTPException(404, "Report not found.")
    person = await _in_scope_person(db, ctx, tid, r.user_id)
    if person.id == ctx.user.id:
        raise HTTPException(403, "Your own report is reviewed by your manager.")
    return r, person


@router.post("/reports/{report_id}/review")
async def review_report(report_id: int, data: ReviewIn,
                        ctx: SecurityContext = Depends(require_permission("report.manage")),
                        db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    r, person = await _team_report(db, ctx, tid, report_id)
    if r.status != "submitted":
        raise HTTPException(409, "You can only review a submitted report.")
    r.reviewed_by = ctx.user.id
    r.reviewed_at = clock_service.now_utc()
    r.review_note = (data.note or "").strip() or None
    await audit.record(db, action="report.reviewed", target_type="daily_report", target_id=r.id,
                       details={"date": r.report_date.isoformat(), "name": person.name}, **ctx.audit_kwargs())
    await notification_service.notify_single_user(
        db, tenant_id=tid, actor_id=ctx.user.id, recipient_id=person.id, event_type="report_reviewed",
        title=f"Your {r.report_date.isoformat()} report was reviewed",
        message=(r.review_note or f"{ctx.user.name} reviewed your day-end report."),
        entity_type="daily_report", entity_id=r.id, entity_name=r.report_date.isoformat())
    await db.commit()
    return _report_view(r, (await _lines_of(db, [r.id])).get(r.id, []), await _report_names(db, [r]))


class ReopenIn(BaseModel):
    note: str = Field(..., min_length=3, max_length=500)


@router.post("/reports/{report_id}/reopen")
async def reopen_report(report_id: int, data: ReopenIn,
                        ctx: SecurityContext = Depends(require_permission("report.manage")),
                        db: AsyncSession = Depends(get_db)):
    """Send a submitted report back to its author as a draft, with what to change."""
    tid = _tid(ctx)
    r, person = await _team_report(db, ctx, tid, report_id)
    if r.status != "submitted":
        raise HTTPException(409, "Only a submitted report can be reopened.")
    r.status = "draft"
    r.submitted_at = None
    r.reviewed_by = r.reviewed_at = r.review_note = None
    r.reopened_by = ctx.user.id
    r.reopened_at = clock_service.now_utc()
    r.reopen_note = data.note.strip()
    await audit.record(db, action="report.reopened", target_type="daily_report", target_id=r.id,
                       details={"date": r.report_date.isoformat(), "name": person.name}, **ctx.audit_kwargs())
    await notification_service.notify_single_user(
        db, tenant_id=tid, actor_id=ctx.user.id, recipient_id=person.id, event_type="report_reopened",
        title=f"Your {r.report_date.isoformat()} report was sent back",
        message=r.reopen_note, entity_type="daily_report", entity_id=r.id,
        entity_name=r.report_date.isoformat())
    await db.commit()
    return _report_view(r, (await _lines_of(db, [r.id])).get(r.id, []), await _report_names(db, [r]))


# ─── admin: assigned work ────────────────────────────────────────────────────

class AssignIn(BaseModel):
    user_id: int
    title: str = Field(..., min_length=2, max_length=200)
    details: str | None = Field(None, max_length=2000)
    priority: Priority = "medium"
    due_date: dt.date | None = None
    start_date: dt.date | None = None
    target_id: int | None = None
    period: Literal["day", "week"] | None = None    # older clients: due today / end of this week


async def _check_target(db, tid: int, target_id: int | None) -> None:
    if target_id is None:
        return
    ok = (await db.execute(select(Target.id).where(Target.id == target_id, Target.tenant_id == tid))).first()
    if not ok:
        raise HTTPException(404, "Target not found.")


@router.post("/assignments", status_code=201)
async def assign_work(data: AssignIn, ctx: SecurityContext = Depends(require_permission("report.manage")),
                      db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    person = await _in_scope_person(db, ctx, tid, data.user_id)
    if person.id == ctx.user.id:
        raise HTTPException(400, "Assign work to the people you oversee, not yourself.")
    await _check_target(db, tid, data.target_id)
    today = clock_service.local_today()
    start = data.start_date or today
    due = data.due_date
    if due is None and data.period:
        due = R.period_bounds(data.period, start)[1]
    if due is not None and due < start:
        raise HTTPException(422, "The due date is before the start date.")
    a = WorkAssignment(tenant_id=tid, user_id=person.id, period=data.period or "day", start_date=start,
                       end_date=due or start, due_date=due, title=data.title.strip(),
                       details=(data.details or "").strip() or None, priority=data.priority,
                       target_id=data.target_id, assigned_by=ctx.user.id)
    db.add(a)
    await db.flush()
    await audit.record(db, action="report.item_assigned", target_type="work_assignment", target_id=a.id,
                       details={"name": person.name, "title": a.title, "priority": a.priority,
                                "due": _iso(due)}, **ctx.audit_kwargs())
    await notification_service.notify_single_user(
        db, tenant_id=tid, actor_id=ctx.user.id, recipient_id=person.id, event_type="work_assigned",
        title=f"New work: {a.title}"[:200],
        message=(f"Due {due.isoformat()}. " if due else "") + (a.details or f"Assigned by {ctx.user.name}. Report on it in My Day."),
        entity_type="work_assignment", entity_id=a.id, entity_name=a.title)
    await db.commit()
    return _assignment_item(a, today, {ctx.user.id: ctx.user.name})


class AssignEdit(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=200)
    details: str | None = Field(None, max_length=2000)
    priority: Priority | None = None
    due_date: dt.date | None = None
    status: Literal["not_started", "in_progress", "blocked", "done", "cancelled"] | None = None
    progress: int | None = Field(None, ge=0, le=100)


async def _team_assignment(db, ctx, tid: int, assignment_id: int) -> WorkAssignment:
    a = (await db.execute(select(WorkAssignment).where(
        WorkAssignment.id == assignment_id, WorkAssignment.tenant_id == tid))).scalars().first()
    if not a:
        raise HTTPException(404, "Assigned item not found.")
    if a.user_id == ctx.user.id:
        raise HTTPException(404, "Assigned item not found.")
    await _in_scope_person(db, ctx, tid, a.user_id)
    return a


@router.patch("/assignments/{assignment_id}")
async def edit_assignment(assignment_id: int, data: AssignEdit,
                          ctx: SecurityContext = Depends(require_permission("report.manage")),
                          db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    a = await _team_assignment(db, ctx, tid, assignment_id)
    changes = data.model_dump(exclude_unset=True)
    today = clock_service.local_today()
    if changes.get("title"):
        a.title = changes["title"].strip()
    if "details" in changes:
        a.details = (changes["details"] or "").strip() or None
    if changes.get("priority"):
        a.priority = changes["priority"]
    if "due_date" in changes:
        if changes["due_date"] and changes["due_date"] < a.start_date:
            raise HTTPException(422, "The due date is before the start date.")
        a.due_date = changes["due_date"]
    if changes.get("status"):
        a.status = changes["status"]
        a.completed_on = today if a.status == "done" else None
        if a.status == "done":
            a.progress = 100
    if changes.get("progress") is not None and a.status != "done":
        a.progress = R.clamp_progress(changes["progress"])
    await audit.record(db, action="report.item_updated", target_type="work_assignment", target_id=a.id,
                       details={"title": a.title, "changed": sorted(changes)}, **ctx.audit_kwargs())
    await db.commit()
    return _assignment_item(a, today, await _names(db, [a.assigned_by]))


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(assignment_id: int, ctx: SecurityContext = Depends(require_permission("report.manage")),
                            db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    a = await _team_assignment(db, ctx, tid, assignment_id)
    await audit.record(db, action="report.item_removed", target_type="work_assignment", target_id=a.id,
                       details={"title": a.title}, **ctx.audit_kwargs())
    await db.delete(a)
    await db.commit()
    return None


# ─── targets and the Gantt ───────────────────────────────────────────────────

async def _milestones_of(db, target_ids: list[int]) -> dict[int, list[TargetMilestone]]:
    if not target_ids:
        return {}
    rows = (await db.execute(select(TargetMilestone).where(
        TargetMilestone.target_id.in_(target_ids)).order_by(TargetMilestone.sort_order, TargetMilestone.id))).scalars().all()
    out: dict[int, list] = {}
    for m in rows:
        out.setdefault(m.target_id, []).append(m)
    return out


def _milestone_view(m: TargetMilestone) -> dict:
    return {"id": m.id, "title": m.title, "due_date": m.due_date.isoformat() if m.due_date else None,
            "done": m.done, "done_at": m.done_at}


def _target_view(t: Target, milestones: list[TargetMilestone], owner_name: str | None,
                 dept_name: str | None, today: dt.date, *, can_manage: bool) -> dict:
    done_ms = sum(1 for m in milestones if m.done)
    return {
        "id": t.id, "title": t.title, "description": t.description,
        "owner_id": t.user_id, "owner": owner_name, "dept_id": t.dept_id, "department": dept_name,
        "scope": "department" if t.user_id is None else "person",
        "start_date": t.start_date.isoformat(), "end_date": t.end_date.isoformat(),
        "progress": t.progress, "status": t.status,
        "state": R.target_state(start=t.start_date, end=t.end_date, progress=t.progress, status=t.status, today=today),
        "expected": R.expected_progress(start=t.start_date, end=t.end_date, today=today),
        "milestones": [_milestone_view(m) for m in milestones],
        "milestones_done": done_ms, "milestones_total": len(milestones),
        "can_manage": can_manage,
    }


async def _target(db, tid: int, target_id: int) -> Target:
    t = (await db.execute(select(Target).where(Target.id == target_id, Target.tenant_id == tid))).scalars().first()
    if not t:
        raise HTTPException(404, "Target not found.")
    return t


async def _owner(db, t: Target) -> User | None:
    if t.user_id is None:
        return None
    return (await db.execute(select(User).where(User.id == t.user_id))).scalars().first()


async def _can_see_target(db, ctx, tid, t: Target) -> bool:
    if t.user_id == ctx.user.id:
        return True
    if not ctx.permissions.has("target.view"):
        return t.user_id == ctx.user.id
    owner = await _owner(db, t)
    if owner is not None:
        return R.can_view_person(ctx.user, owner, tid)
    # Department target: visible to org-wide admins, and to a Department Admin of that department.
    if ctx.user.role == "org_admin" and not ctx.permissions.grants_all:
        return t.dept_id == ctx.user.dept_id
    return True


async def _render_targets(db, ctx, tid, targets: list[Target]) -> list[dict]:
    ms = await _milestones_of(db, [t.id for t in targets])
    names = await _names(db, [t.user_id for t in targets])
    depts = {d.department_id: d.department_name for d in (await db.execute(
        select(Department).where(Department.tenant_id == tid))).scalars().all()}
    today = clock_service.local_today()
    has_manage = ctx.permissions.has("target.manage")
    out = []
    for t in targets:
        owner = None
        if t.user_id:
            owner = await _owner(db, t)
        can_manage = R.can_manage_target(ctx.user, t.user_id, owner, has_manage, tid)
        out.append(_target_view(t, ms.get(t.id, []), names.get(t.user_id), depts.get(t.dept_id), today,
                                can_manage=can_manage))
    return out


@router.get("/me/targets")
async def my_targets(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    conds = [Target.user_id == ctx.user.id]
    if ctx.user.dept_id:
        conds.append(Target.dept_id == ctx.user.dept_id)      # department targets I share in
    targets = (await db.execute(select(Target).where(
        Target.tenant_id == tid, or_(*conds)).order_by(Target.start_date))).scalars().all()
    return await _render_targets(db, ctx, tid, targets)


@router.get("/targets")
async def all_targets(user_id: int | None = None, status: str | None = None,
                      ctx: SecurityContext = Depends(require_permission("target.view")),
                      db: AsyncSession = Depends(get_db)):
    """Everything in the caller's scope, for the Gantt timeline."""
    tid = _tid(ctx)
    people = await _overseen(db, ctx, tid)
    ids = [u.id for u in people] + [ctx.user.id]
    conds = [Target.user_id.in_(ids)]
    # Department targets the caller can see.
    if ctx.user.role == "org_admin" and not ctx.permissions.grants_all:
        if ctx.user.dept_id:
            conds.append((Target.user_id.is_(None)) & (Target.dept_id == ctx.user.dept_id))
    else:
        conds.append(Target.user_id.is_(None))
    q = select(Target).where(Target.tenant_id == tid, or_(*conds))
    if user_id:
        q = q.where(Target.user_id == user_id)
    if status:
        q = q.where(Target.status == status)
    targets = (await db.execute(q.order_by(Target.start_date, Target.id))).scalars().all()
    return await _render_targets(db, ctx, tid, targets)


class MilestoneIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due_date: dt.date | None = None


class TargetIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str | None = Field(None, max_length=5000)
    user_id: int | None = None          # person target
    dept_id: int | None = None          # or department target
    start_date: dt.date
    end_date: dt.date
    milestones: list[MilestoneIn] = Field(default_factory=list, max_length=30)


@router.post("/targets", status_code=201)
async def create_target(data: TargetIn, ctx: SecurityContext = Depends(require_permission("target.manage")),
                        db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    if data.end_date < data.start_date:
        raise HTTPException(422, "The end date is before the start date.")
    if (data.user_id is None) == (data.dept_id is None):
        raise HTTPException(422, "Give a target to a person or a department, not both or neither.")

    owner = None
    if data.user_id is not None:
        owner = await _in_scope_person(db, ctx, tid, data.user_id)
    else:
        d = (await db.execute(select(Department).where(
            Department.department_id == data.dept_id, Department.tenant_id == tid))).scalars().first()
        if not d:
            raise HTTPException(404, "Department not found.")
        if ctx.user.role == "org_admin" and not ctx.permissions.grants_all and d.department_id != ctx.user.dept_id:
            raise HTTPException(403, "You can only set targets for your own department.")

    t = Target(tenant_id=tid, user_id=data.user_id, dept_id=data.dept_id, title=data.title.strip(),
               description=(data.description or "").strip() or None, start_date=data.start_date,
               end_date=data.end_date, created_by=ctx.user.id)
    db.add(t)
    await db.flush()
    for i, m in enumerate(data.milestones):
        db.add(TargetMilestone(target_id=t.id, title=m.title.strip(), due_date=m.due_date, sort_order=i))
    await audit.record(db, action="target.created", target_type="target", target_id=t.id,
                       details={"title": t.title, "owner_id": data.user_id, "dept_id": data.dept_id},
                       **ctx.audit_kwargs())
    if owner:
        await notification_service.notify_single_user(
            db, tenant_id=tid, actor_id=ctx.user.id, recipient_id=owner.id, event_type="target_assigned",
            title=f"New target: {t.title}",
            message=f"Due {t.end_date.isoformat()}. Track it under My Targets.",
            entity_type="target", entity_id=t.id, entity_name=t.title)
    await db.commit()
    return (await _render_targets(db, ctx, tid, [t]))[0]


@router.get("/targets/{target_id}")
async def get_target(target_id: int, ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    if not await _can_see_target(db, ctx, tid, t):
        raise HTTPException(404, "Target not found.")
    view = (await _render_targets(db, ctx, tid, [t]))[0]
    updates = (await db.execute(select(TargetUpdate).where(TargetUpdate.target_id == t.id)
                                .order_by(TargetUpdate.created_at.desc()).limit(50))).scalars().all()
    who = await _names(db, [u.user_id for u in updates])
    view["history"] = [{"progress": u.progress, "note": u.note, "by": who.get(u.user_id),
                        "at": u.created_at} for u in updates]
    return view


class TargetEdit(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = Field(None, max_length=5000)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    status: Literal["active", "done", "cancelled"] | None = None


async def _require_manage_target(db, ctx, tid, t: Target) -> User | None:
    owner = await _owner(db, t)
    if not R.can_manage_target(ctx.user, t.user_id, owner, ctx.permissions.has("target.manage"), tid):
        raise HTTPException(404, "Target not found.")
    return owner


@router.patch("/targets/{target_id}")
async def edit_target(target_id: int, data: TargetEdit, ctx: SecurityContext = Depends(get_security_context),
                      db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    await _require_manage_target(db, ctx, tid, t)
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if v is not None:
            setattr(t, k, v)
    if t.end_date < t.start_date:
        raise HTTPException(422, "The end date is before the start date.")
    await audit.record(db, action="target.updated", target_type="target", target_id=t.id,
                       details={"title": t.title, "changed": sorted(changes)}, **ctx.audit_kwargs())
    await db.commit()
    return (await _render_targets(db, ctx, tid, [t]))[0]


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(target_id: int, ctx: SecurityContext = Depends(require_permission("target.manage")),
                        db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    await _require_manage_target(db, ctx, tid, t)
    await audit.record(db, action="target.deleted", target_type="target", target_id=t.id,
                       details={"title": t.title}, **ctx.audit_kwargs())
    await db.delete(t)
    await db.commit()
    return None


class ProgressIn(BaseModel):
    progress: int = Field(..., ge=0, le=100)
    note: str | None = Field(None, max_length=1000)


async def _update_progress(db, ctx, tid, t: Target, data: ProgressIn):
    t.progress = R.clamp_progress(data.progress)
    if t.progress >= 100 and t.status == "active":
        t.status = "done"
    elif t.progress < 100 and t.status == "done":
        t.status = "active"
    db.add(TargetUpdate(target_id=t.id, user_id=ctx.user.id, progress=t.progress,
                        note=(data.note or "").strip() or None))
    await audit.record(db, action="target.progress_updated", target_type="target", target_id=t.id,
                       details={"title": t.title, "progress": t.progress}, **ctx.audit_kwargs())
    await db.commit()
    return (await _render_targets(db, ctx, tid, [t]))[0]


@router.post("/targets/{target_id}/progress")
async def set_progress(target_id: int, data: ProgressIn, ctx: SecurityContext = Depends(get_security_context),
                       db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    await _require_manage_target(db, ctx, tid, t)
    return await _update_progress(db, ctx, tid, t, data)


@router.post("/me/targets/{target_id}/progress")
async def set_my_progress(target_id: int, data: ProgressIn, ctx: SecurityContext = Depends(get_security_context),
                          db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    if t.user_id != ctx.user.id:
        raise HTTPException(404, "Target not found.")
    return await _update_progress(db, ctx, tid, t, data)


@router.post("/targets/{target_id}/milestones", status_code=201)
async def add_milestone(target_id: int, data: MilestoneIn, ctx: SecurityContext = Depends(get_security_context),
                        db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    await _require_manage_target(db, ctx, tid, t)
    n = (await db.execute(select(func.count(TargetMilestone.id)).where(TargetMilestone.target_id == t.id))).scalar() or 0
    m = TargetMilestone(target_id=t.id, title=data.title.strip(), due_date=data.due_date, sort_order=n)
    db.add(m)
    await db.flush()
    await audit.record(db, action="target.updated", target_type="target", target_id=t.id,
                       details={"title": t.title, "milestone_added": m.title}, **ctx.audit_kwargs())
    await db.commit()
    return _milestone_view(m)


class MilestoneEdit(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    due_date: dt.date | None = None
    done: bool | None = None


@router.patch("/targets/{target_id}/milestones/{milestone_id}")
async def edit_milestone(target_id: int, milestone_id: int, data: MilestoneEdit,
                         ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    # The owner may tick milestones; editing text/date needs manage rights.
    owner = await _owner(db, t)
    is_owner = t.user_id == ctx.user.id
    can_manage = R.can_manage_target(ctx.user, t.user_id, owner, ctx.permissions.has("target.manage"), tid)
    if not (is_owner or can_manage):
        raise HTTPException(404, "Target not found.")
    m = (await db.execute(select(TargetMilestone).where(
        TargetMilestone.id == milestone_id, TargetMilestone.target_id == t.id))).scalars().first()
    if not m:
        raise HTTPException(404, "Milestone not found.")
    changes = data.model_dump(exclude_unset=True)
    if ("title" in changes or "due_date" in changes) and not can_manage:
        raise HTTPException(403, "Only an admin can change a milestone's text or date.")
    if "done" in changes and changes["done"] is not None:
        m.done = changes["done"]
        m.done_at = clock_service.now_utc() if m.done else None
    if changes.get("title"):
        m.title = changes["title"].strip()
    if "due_date" in changes:
        m.due_date = changes["due_date"]
    await db.commit()
    return _milestone_view(m)


@router.delete("/targets/{target_id}/milestones/{milestone_id}", status_code=204)
async def delete_milestone(target_id: int, milestone_id: int,
                           ctx: SecurityContext = Depends(require_permission("target.manage")),
                           db: AsyncSession = Depends(get_db)):
    tid = _tid(ctx)
    t = await _target(db, tid, target_id)
    await _require_manage_target(db, ctx, tid, t)
    m = (await db.execute(select(TargetMilestone).where(
        TargetMilestone.id == milestone_id, TargetMilestone.target_id == t.id))).scalars().first()
    if m:
        await db.delete(m)
        await db.commit()
    return None
