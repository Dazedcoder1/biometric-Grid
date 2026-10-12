"""
Payroll runs: gathering a month's facts from the database and turning them
into payslips with payroll_calc.

A run moves draft -> submitted -> closed.

  prepare / recompute   draft only. Re-reads attendance, leave, holidays,
                        structures and approved claims, and rebuilds every
                        payslip. An admin's LOP override and one-off
                        adjustments on an entry survive a recompute.
  submit                draft -> submitted. The submitter is the maker.
  approve               submitted -> closed, by someone OTHER than the maker.
                        Claims in the run become paid. A closed run is never
                        recomputed — its payslips are what was paid.
  return                submitted -> draft, with a note saying why.

Nothing here commits; the routes do, after writing the audit entry.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import and_, select

from app.models.domain import (
    Department,
    EmployeePayProfile,
    Holiday,
    Leave,
    PayComponent,
    PayrollEntry,
    PayrollRun,
    Reimbursement,
    SalaryRevision,
    Settings,
    Tenant,
    User,
)
from app.services import clock_service
from app.services import payroll_calc as calc

PAYROLL_ROLES = ("employee", "org_admin")


def component_dict(c: PayComponent) -> dict:
    return {
        "id": c.id, "code": c.code, "name": c.name, "kind": c.kind, "calc": c.calc,
        "rate": float(c.rate) if c.rate is not None else None,
        "employer_rate": float(c.employer_rate) if c.employer_rate is not None else None,
        "base_codes": c.base_codes,
        "wage_ceiling": float(c.wage_ceiling) if c.wage_ceiling is not None else None,
        "gross_limit": float(c.gross_limit) if c.gross_limit is not None else None,
        "slabs": c.slabs, "prorate": bool(c.prorate), "applies_to": c.applies_to,
        "is_statutory": bool(c.is_statutory), "active": bool(c.active), "sort_order": c.sort_order,
    }


async def components_for(db, tenant_id: int) -> list[dict]:
    rows = (await db.execute(
        select(PayComponent).where(PayComponent.tenant_id == tenant_id)
        .order_by(PayComponent.sort_order, PayComponent.code)
    )).scalars().all()
    return [component_dict(c) for c in rows]


async def revision_in_force(db, tenant_id: int, user_ids: list[int], on: dt.date) -> dict[int, SalaryRevision]:
    """Latest revision effective on or before `on`, per person."""
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(SalaryRevision)
        .where(SalaryRevision.tenant_id == tenant_id, SalaryRevision.user_id.in_(user_ids),
               SalaryRevision.effective_from <= on)
        .order_by(SalaryRevision.user_id, SalaryRevision.effective_from, SalaryRevision.id)
    )).scalars().all()
    out: dict[int, SalaryRevision] = {}
    for r in rows:
        out[r.user_id] = r                              # ordered, so the last one wins
    return out


async def get_run(db, tenant_id: int, run_id: int) -> PayrollRun:
    run = (await db.execute(
        select(PayrollRun).where(PayrollRun.id == run_id, PayrollRun.tenant_id == tenant_id)
    )).scalars().first()
    if not run:
        raise HTTPException(404, "Payroll run not found.")
    return run


def _require(run: PayrollRun, *statuses: str, doing: str) -> None:
    if run.status not in statuses:
        raise HTTPException(409, f"Cannot {doing}: this month is {run.status}.")


# ─── preparing ───────────────────────────────────────────────────────────────

async def _people(db, tenant_id: int, on: dt.date) -> list[User]:
    """Active employees and Org Admins, plus anyone else with a structure in force."""
    with_structure = select(SalaryRevision.user_id).where(
        SalaryRevision.tenant_id == tenant_id, SalaryRevision.effective_from <= on)
    return list((await db.execute(
        select(User).where(
            User.tenant_id == tenant_id, User.is_active.is_(True),
            (User.role.in_(PAYROLL_ROLES)) | (User.id.in_(with_structure)),
        ).order_by(User.name)
    )).scalars().all())


async def _month_facts(db, tenant_id: int, people: list[User], period: dt.date):
    end = calc.month_end(period)
    ids = [u.id for u in people]

    hol_rows = (await db.execute(
        select(Holiday.holiday_date).where(
            Holiday.tenant_id == tenant_id,
            Holiday.holiday_date >= dt.datetime.combine(period, dt.time.min),
            Holiday.holiday_date < dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min),
        )
    )).scalars().all()
    holidays = {h.date() if isinstance(h, dt.datetime) else h for h in hol_rows}

    leave_days: dict[int, dict[dt.date, str]] = defaultdict(dict)
    if ids:
        leaves = (await db.execute(
            select(Leave).where(
                Leave.tenant_id == tenant_id, Leave.employee_id.in_(ids), Leave.status == "approved",
                Leave.start_date < dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min),
                Leave.end_date >= dt.datetime.combine(period, dt.time.min),
            )
        )).scalars().all()
        for lv in leaves:
            d = max(lv.start_date.date(), period)
            last = min(lv.end_date.date(), end)
            while d <= last:
                leave_days[lv.employee_id][d] = lv.leave_type or ""
                d += dt.timedelta(days=1)

    start_utc, _ = clock_service.day_bounds(period)
    _, end_utc = clock_service.day_bounds(end)
    punches = await clock_service.punches_between(db, tenant_id, people, start_utc, end_utc)
    tz = clock_service.zone()
    present = {
        uid: {clock_service.aware(p.timestamp).astimezone(tz).date() for p in rows if p.record_type == "IN"}
        for uid, rows in punches.items()
    }

    settings = (await db.execute(select(Settings).where(Settings.tenant_id == tenant_id))).scalars().first()
    weekdays = calc.working_weekdays(settings.working_days if settings else None)
    return holidays, leave_days, present, weekdays


async def prepare(db, tenant_id: int, period: dt.date, actor: User, run: PayrollRun | None = None) -> PayrollRun:
    today = clock_service.local_today()
    if period > today.replace(day=1):
        raise HTTPException(400, "That month has not started yet.")

    if run is None:
        run = (await db.execute(
            select(PayrollRun).where(PayrollRun.tenant_id == tenant_id, PayrollRun.period == period)
        )).scalars().first()
    if run is None:
        run = PayrollRun(tenant_id=tenant_id, period=period, status="draft")
        db.add(run)
        await db.flush()
    _require(run, "draft", doing="recalculate")

    end = calc.month_end(period)
    people = await _people(db, tenant_id, end)
    ids = [u.id for u in people]
    components = await components_for(db, tenant_id)
    revisions = await revision_in_force(db, tenant_id, ids, end)
    profiles = {p.user_id: p for p in (await db.execute(
        select(EmployeePayProfile).where(EmployeePayProfile.tenant_id == tenant_id,
                                         EmployeePayProfile.user_id.in_(ids or [0]))
    )).scalars().all()}
    depts = {d.department_id: d.department_name for d in (await db.execute(
        select(Department).where(Department.tenant_id == tenant_id))).scalars().all()}
    holidays, leave_days, present, weekdays = await _month_facts(db, tenant_id, people, period)

    # Approved claims not yet paid in another run join this one.
    claims = (await db.execute(
        select(Reimbursement).where(
            Reimbursement.tenant_id == tenant_id, Reimbursement.status == "approved",
            (Reimbursement.payroll_run_id.is_(None)) | (Reimbursement.payroll_run_id == run.id),
        )
    )).scalars().all()
    claims_by_user: dict[int, list[Reimbursement]] = defaultdict(list)
    for r in claims:
        claims_by_user[r.user_id].append(r)
        r.payroll_run_id = run.id

    existing = {e.user_id: e for e in (await db.execute(
        select(PayrollEntry).where(PayrollEntry.run_id == run.id))).scalars().all()}

    totals = defaultdict(float)
    for u in people:
        prof = profiles.get(u.id)
        rev = revisions.get(u.id)
        joined = prof.date_of_joining if prof and prof.date_of_joining else None
        days = calc.count_days(
            period, today=today, joined=joined, holidays=holidays,
            leave_days=leave_days.get(u.id, {}), present=present.get(u.id, set()), weekdays=weekdays,
        )
        entry = existing.pop(u.id, None)
        override = entry.lop_override if entry else None
        paid, lop = calc.paid_days(days, override)
        pay_type = prof.pay_type if prof else "salary"
        exempt = set(calc._codes(prof.exempt_codes)) if prof else set()
        pay = calc.compute_pay(
            components, rev.lines if rev else {}, pay_type=pay_type, exempt=exempt,
            days_in_month=days["days_in_month"], paid=paid,
            adjustments=(entry.adjustments if entry else None) or [],
            reimbursements=[{"id": r.id, "category": r.category, "amount": r.amount}
                            for r in claims_by_user.get(u.id, [])],
        )
        data = {
            "employee": {
                "user_id": u.id, "name": u.name, "employee_code": u.employee_code, "email": u.email,
                "department": depts.get(u.dept_id), "role": u.role, "pay_type": pay_type,
                "designation": prof.designation if prof else None,
                "date_of_joining": joined.isoformat() if joined else None,
                "pan": prof.pan if prof else None, "uan": prof.uan if prof else None,
                "pf_number": prof.pf_number if prof else None,
                "esic_number": prof.esic_number if prof else None,
                "pt_state": prof.pt_state if prof else None,
                "bank_name": prof.bank_name if prof else None,
                "bank_account": prof.bank_account if prof else None,
                "bank_ifsc": prof.bank_ifsc if prof else None,
            },
            "days": {**days, "paid_days": float(paid), "lop_days": float(lop),
                     "lop_overridden": override is not None},
            "structure": {
                "revision_id": rev.id if rev else None,
                "effective_from": rev.effective_from.isoformat() if rev else None,
                "annual_ctc": float(rev.annual_ctc) if rev else 0.0,
                "monthly_fixed": float(sum(calc.D(v) for v in (rev.lines or {}).values())) if rev else 0.0,
            },
            **pay,
        }
        if entry is None:
            entry = PayrollEntry(run_id=run.id, tenant_id=tenant_id, user_id=u.id)
            db.add(entry)
        entry.data = data
        entry.gross = pay["gross"]
        entry.net_pay = pay["net_pay"]
        totals["people"] += 1
        for key in ("gross", "total_deductions", "reimbursement_total", "net_pay", "employer_total"):
            totals[key] += pay[key]
        totals["warnings"] += 1 if pay["warnings"] else 0

    # People no longer in scope (left, deactivated) drop out of a draft.
    for gone in existing.values():
        await db.delete(gone)

    run.totals = {k: round(v, 2) for k, v in totals.items()}
    run.prepared_by = actor.id
    run.prepared_at = clock_service.now_utc()
    run.returned_note = None
    return run


# ─── maker-checker ───────────────────────────────────────────────────────────

def submit(run: PayrollRun, actor: User) -> None:
    _require(run, "draft", doing="submit")
    if not run.totals or not run.totals.get("people"):
        raise HTTPException(409, "Nothing to submit: prepare the month first.")
    run.status = "submitted"
    run.submitted_by = actor.id
    run.submitted_at = clock_service.now_utc()


async def approve(db, run: PayrollRun, actor: User) -> None:
    _require(run, "submitted", doing="approve")
    if actor.id == run.submitted_by:
        raise HTTPException(
            403, "You submitted this month, so someone else has to approve it (maker-checker).",
        )
    run.status = "closed"
    run.approved_by = actor.id
    run.approved_at = clock_service.now_utc()
    claims = (await db.execute(
        select(Reimbursement).where(Reimbursement.payroll_run_id == run.id,
                                    Reimbursement.status == "approved")
    )).scalars().all()
    for r in claims:
        r.status = "paid"


def send_back(run: PayrollRun, note: str) -> None:
    _require(run, "submitted", doing="send back")
    run.status = "draft"
    run.returned_note = note
    run.submitted_by = None
    run.submitted_at = None


# ─── reading ─────────────────────────────────────────────────────────────────

def mask(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return value
    return "•" * max(0, len(value) - keep) + value[-keep:]


def entry_view(e: PayrollEntry, *, full: bool = False) -> dict:
    """An entry for the screen. Bank account masked unless `full`."""
    data = dict(e.data or {})
    emp = dict(data.get("employee") or {})
    if not full:
        emp["bank_account"] = mask(emp.get("bank_account"))
    data["employee"] = emp
    return {
        "id": e.id, "run_id": e.run_id, "user_id": e.user_id, **data,
        "lop_override": float(e.lop_override) if e.lop_override is not None else None,
        "override_note": e.override_note, "adjustments": e.adjustments or [],
    }


async def names(db, ids) -> dict[int, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {u.id: u.name for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()}


async def run_view(db, run: PayrollRun) -> dict:
    who = await names(db, [run.prepared_by, run.submitted_by, run.approved_by])
    return {
        "id": run.id, "period": run.period.strftime("%Y-%m"), "label": calc.period_label(run.period),
        "status": run.status, "totals": run.totals or {},
        "prepared_by": who.get(run.prepared_by), "prepared_at": run.prepared_at,
        "submitted_by": who.get(run.submitted_by), "submitted_by_id": run.submitted_by,
        "submitted_at": run.submitted_at,
        "approved_by": who.get(run.approved_by), "approved_at": run.approved_at,
        "returned_note": run.returned_note,
    }


async def tenant_name(db, tenant_id: int) -> str:
    t = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalars().first()
    return t.name if t else ""


async def entries_for(db, run_id: int) -> list[PayrollEntry]:
    return list((await db.execute(
        select(PayrollEntry).where(PayrollEntry.run_id == run_id).order_by(PayrollEntry.id)
    )).scalars().all())


async def entry_in_run(db, run: PayrollRun, entry_id: int) -> PayrollEntry:
    e = (await db.execute(
        select(PayrollEntry).where(and_(PayrollEntry.id == entry_id, PayrollEntry.run_id == run.id))
    )).scalars().first()
    if not e:
        raise HTTPException(404, "Payslip not found in this month.")
    return e
