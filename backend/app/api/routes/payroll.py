"""
Payroll management — /api/payroll.

Setup (payroll.manage to change, payroll.view to read)
    /components                       the organisation's earnings and deductions
    /people, /people/{id}             pay profile, compliance fields, revisions
    /people/{id}/profile              PUT
    /people/{id}/revisions            POST — append a salary revision

Months (maker-checker; see services/payroll_service.py)
    /runs                             list, or POST {period} to prepare a month
    /runs/{id}                        the month and every payslip in it
    /runs/{id}/recompute              re-read attendance, leave, claims
    /runs/{id}/entries/{eid}          PATCH: LOP override, one-off adjustments
    /runs/{id}/submit                 maker
    /runs/{id}/approve                checker — never the maker; closes the month
    /runs/{id}/return                 back to draft with a reason
    /runs/{id}/register.csv           for accounting (full bank details)
    /runs/{id}/summary.csv            component totals for the journal
    /runs/{id}/entries/{eid}/payslip.pdf

Expense claims
    /reimbursements                   claims awaiting a decision, in scope
    /reimbursements/{id}/decide       approve or reject

Self-service — anyone in an organisation
    /me                               my structure, revision history, profile
    /me/payslips, /me/payslips/{eid}/payslip.pdf   closed months only
    /me/reimbursements                my claims; POST to submit one
    /me/reimbursements/{id}           DELETE to withdraw a pending claim

Every change and every export is in the audit log. Bank account numbers are
masked everywhere except the register export and the payslip's last four.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
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
    EmployeePayProfile,
    PayComponent,
    PayrollEntry,
    PayrollRun,
    Reimbursement,
    SalaryRevision,
    User,
)
from app.services import clock_service, payroll_docs
from app.services import payroll_calc as calc
from app.services import payroll_service as svc

router = APIRouter()

CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")


# ─── helpers ─────────────────────────────────────────────────────────────────

async def _person(db, tenant_id: int, user_id: int) -> User:
    u = (await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))).scalars().first()
    if not u:
        raise HTTPException(404, "Person not found in this organisation.")
    return u


def _not_own_pay(ctx: SecurityContext, user_id: int | None) -> None:
    """Nobody sets their own pay. An HR person, or an Org Admin with HR access,
    runs payroll for everyone else; someone else changes theirs."""
    if user_id is not None and user_id == ctx.user.id:
        raise HTTPException(403, "You cannot change your own pay — ask another payroll administrator.")


def _own_tenant(ctx: SecurityContext) -> int:
    if ctx.user.tenant_id is None:
        raise HTTPException(409, "Payroll self-service is for people in an organisation.")
    return ctx.user.tenant_id


def _csv(text: str, filename: str) -> Response:
    # BOM so Excel opens the UTF-8 file with the right encoding (names, "—").
    return Response("﻿" + text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pdf(data: bytes, filename: str) -> Response:
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")[:40] or "payslip"


# ─── components ──────────────────────────────────────────────────────────────

class Slab(BaseModel):
    upto: float | None = Field(None, ge=0)
    amount: float = Field(..., ge=0)


class ComponentIn(BaseModel):
    code: str
    name: str = Field(..., min_length=1, max_length=80)
    kind: Literal["earning", "deduction"]
    calc: Literal["fixed", "percent", "slab"] = "fixed"
    rate: float | None = Field(None, ge=0, le=100)
    employer_rate: float | None = Field(None, ge=0, le=100)
    base_codes: str | None = Field(None, max_length=255)
    wage_ceiling: float | None = Field(None, ge=0)
    gross_limit: float | None = Field(None, ge=0)
    slabs: list[Slab] | None = Field(None, max_length=20)
    prorate: bool = True
    applies_to: Literal["all", "salary", "stipend"] = "all"
    is_statutory: bool = False
    active: bool = True
    sort_order: int = Field(100, ge=0, le=10000)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip().upper()
        if not CODE.match(v):
            raise ValueError("Code: 2–32 capital letters, digits or _, starting with a letter (e.g. BASIC, PF).")
        if v in ("GROSS", "ADJ"):
            raise ValueError(f"{v} is reserved.")
        return v

    @field_validator("base_codes")
    @classmethod
    def _base(cls, v):
        if v is None:
            return v
        return ",".join(c.strip().upper() for c in v.split(",") if c.strip()) or None


class ComponentPatch(ComponentIn):
    code: str | None = None                          # the code never changes: structures refer to it
    name: str | None = Field(None, min_length=1, max_length=80)
    kind: Literal["earning", "deduction"] | None = None


def _check_component(data: dict) -> None:
    if data.get("calc") == "percent" and data.get("rate") is None:
        raise HTTPException(422, "A percentage component needs a rate.")
    if data.get("calc") == "slab" and not data.get("slabs"):
        raise HTTPException(422, "A slab component needs at least one slab.")
    if data.get("calc") == "slab":
        open_top = [s for s in data["slabs"] if s.get("upto") is None]
        if len(open_top) > 1:
            raise HTTPException(422, "Only one slab can be open-ended (no upper limit).")


@router.get("/components")
async def list_components(ctx: SecurityContext = Depends(require_permission("payroll.view")),
                          db: AsyncSession = Depends(get_db)):
    return await svc.components_for(db, require_organisation(ctx))


@router.post("/components", status_code=201)
async def create_component(data: ComponentIn,
                           ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                           db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    body = data.model_dump()
    body["slabs"] = body["slabs"] or None
    _check_component(body)
    clash = (await db.execute(select(PayComponent).where(
        PayComponent.tenant_id == tid, PayComponent.code == data.code))).scalars().first()
    if clash:
        raise HTTPException(409, f"A component with code {data.code} already exists.")
    c = PayComponent(tenant_id=tid, **body)
    db.add(c)
    await db.flush()
    await audit.record(db, action="payroll.component_created", target_type="pay_component",
                       target_id=c.id, details={"code": c.code, "name": c.name, "kind": c.kind},
                       **ctx.audit_kwargs())
    await db.commit()
    return svc.component_dict(c)


@router.patch("/components/{component_id}")
async def update_component(component_id: int, data: ComponentPatch,
                           ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                           db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    c = (await db.execute(select(PayComponent).where(
        PayComponent.id == component_id, PayComponent.tenant_id == tid))).scalars().first()
    if not c:
        raise HTTPException(404, "Component not found.")
    changes = data.model_dump(exclude_unset=True, exclude={"code"})
    merged = {**svc.component_dict(c), **changes}
    _check_component(merged)
    for k, v in changes.items():
        setattr(c, k, v)
    await audit.record(db, action="payroll.component_updated", target_type="pay_component",
                       target_id=c.id, details={"code": c.code, "changed": sorted(changes)},
                       **ctx.audit_kwargs())
    await db.commit()
    return svc.component_dict(c)


# ─── people: profiles and salary revisions ───────────────────────────────────

def _profile_view(p: EmployeePayProfile | None, *, full: bool) -> dict:
    if p is None:
        return {"pay_type": "salary", "exempt_codes": []}
    return {
        "pay_type": p.pay_type, "designation": p.designation,
        "date_of_joining": p.date_of_joining.isoformat() if p.date_of_joining else None,
        "pan": p.pan, "uan": p.uan, "pf_number": p.pf_number, "esic_number": p.esic_number,
        "pt_state": p.pt_state, "bank_name": p.bank_name,
        "bank_account": p.bank_account if full else svc.mask(p.bank_account),
        "bank_ifsc": p.bank_ifsc, "exempt_codes": calc._codes(p.exempt_codes),
    }


def _revision_view(r: SalaryRevision, names: dict[int, str], comp_names: dict[str, str]) -> dict:
    lines = r.lines or {}
    return {
        "id": r.id, "effective_from": r.effective_from.isoformat(), "annual_ctc": float(r.annual_ctc),
        "monthly_fixed": float(sum(calc.D(v) for v in lines.values())),
        "lines": [{"code": k, "name": comp_names.get(k, k), "amount": float(v)} for k, v in lines.items()],
        "reason": r.reason, "created_by": names.get(r.created_by), "created_at": r.created_at,
    }


def _missing(profile: dict) -> list[str]:
    need = ["date_of_joining", "pan", "bank_account", "bank_ifsc"]
    return [k for k in need if not profile.get(k)]


@router.get("/people")
async def list_people(ctx: SecurityContext = Depends(require_permission("payroll.view")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    today = clock_service.local_today()
    people = await svc._people(db, tid, today)
    ids = [u.id for u in people]
    current = await svc.revision_in_force(db, tid, ids, today)
    profiles = {p.user_id: p for p in (await db.execute(select(EmployeePayProfile).where(
        EmployeePayProfile.tenant_id == tid, EmployeePayProfile.user_id.in_(ids or [0])))).scalars().all()}
    depts = await _dept_names(db, tid)
    out = []
    for u in people:
        prof = _profile_view(profiles.get(u.id), full=False)
        rev = current.get(u.id)
        out.append({
            "user_id": u.id, "name": u.name, "employee_code": u.employee_code, "role": u.role,
            "department": depts.get(u.dept_id), "pay_type": prof["pay_type"],
            "designation": prof.get("designation"),
            "annual_ctc": float(rev.annual_ctc) if rev else None,
            "monthly_fixed": float(sum(calc.D(v) for v in (rev.lines or {}).values())) if rev else None,
            "effective_from": rev.effective_from.isoformat() if rev else None,
            "missing": _missing(prof) + ([] if rev else ["salary structure"]),
        })
    return out


async def _dept_names(db, tid):
    from app.models.domain import Department
    return {d.department_id: d.department_name for d in (await db.execute(
        select(Department).where(Department.tenant_id == tid))).scalars().all()}


async def _person_detail(db, tid: int, u: User, *, full: bool) -> dict:
    prof = (await db.execute(select(EmployeePayProfile).where(
        EmployeePayProfile.user_id == u.id))).scalars().first()
    revs = (await db.execute(select(SalaryRevision).where(
        SalaryRevision.tenant_id == tid, SalaryRevision.user_id == u.id)
        .order_by(SalaryRevision.effective_from.desc(), SalaryRevision.id.desc()))).scalars().all()
    who = await svc.names(db, [r.created_by for r in revs])
    comp_names = {c["code"]: c["name"] for c in await svc.components_for(db, tid)}
    today = clock_service.local_today()
    current = next((r for r in revs if r.effective_from <= today), None)
    depts = await _dept_names(db, tid)
    return {
        "user_id": u.id, "name": u.name, "employee_code": u.employee_code, "email": u.email,
        "role": u.role, "department": depts.get(u.dept_id),
        "profile": _profile_view(prof, full=full),
        "current": _revision_view(current, who, comp_names) if current else None,
        "revisions": [_revision_view(r, who, comp_names) for r in revs],
    }


@router.get("/people/{user_id}")
async def get_person(user_id: int, ctx: SecurityContext = Depends(require_permission("payroll.view")),
                     db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    u = await _person(db, tid, user_id)
    return await _person_detail(db, tid, u, full=ctx.permissions.has("payroll.manage"))


class ProfileIn(BaseModel):
    pay_type: Literal["salary", "stipend"] = "salary"
    designation: str | None = Field(None, max_length=80)
    date_of_joining: dt.date | None = None
    pan: str | None = None
    uan: str | None = None
    pf_number: str | None = Field(None, max_length=32)
    esic_number: str | None = None
    pt_state: str | None = Field(None, max_length=40)
    bank_name: str | None = Field(None, max_length=80)
    bank_account: str | None = None
    bank_ifsc: str | None = None
    exempt_codes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("pan", "uan", "esic_number", "bank_account", "bank_ifsc", "pf_number", mode="before")
    @classmethod
    def _blank(cls, v):
        if isinstance(v, str):
            v = v.strip().upper().replace(" ", "")
            return v or None
        return v

    @field_validator("pan")
    @classmethod
    def _pan(cls, v):
        if v and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", v):
            raise ValueError("PAN looks like ABCDE1234F.")
        return v

    @field_validator("uan")
    @classmethod
    def _uan(cls, v):
        if v and not re.fullmatch(r"\d{12}", v):
            raise ValueError("UAN is 12 digits.")
        return v

    @field_validator("esic_number")
    @classmethod
    def _esic(cls, v):
        if v and not re.fullmatch(r"\d{10,17}", v):
            raise ValueError("ESIC number is 10 to 17 digits.")
        return v

    @field_validator("bank_account")
    @classmethod
    def _acct(cls, v):
        if v and not re.fullmatch(r"\d{6,18}", v):
            raise ValueError("Bank account number is 6 to 18 digits.")
        return v

    @field_validator("bank_ifsc")
    @classmethod
    def _ifsc(cls, v):
        if v and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", v):
            raise ValueError("IFSC looks like HDFC0001234.")
        return v


@router.put("/people/{user_id}/profile")
async def save_profile(user_id: int, data: ProfileIn,
                       ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    _not_own_pay(ctx, user_id)
    u = await _person(db, tid, user_id)
    p = (await db.execute(select(EmployeePayProfile).where(EmployeePayProfile.user_id == u.id))).scalars().first()
    if p is None:
        p = EmployeePayProfile(tenant_id=tid, user_id=u.id)
        db.add(p)
    body = data.model_dump()
    exempt = ",".join(sorted({c.strip().upper() for c in body.pop("exempt_codes") if c.strip()})) or None
    before = _profile_view(p, full=True) if p.id else {}
    for k, v in body.items():
        setattr(p, k, v)
    p.exempt_codes = exempt
    after = _profile_view(p, full=True)
    changed = sorted(k for k in after if before.get(k) != after.get(k))
    await audit.record(db, action="payroll.profile_updated", target_type="user", target_id=u.id,
                       details={"name": u.name, "changed": changed}, **ctx.audit_kwargs())
    await db.commit()
    return await _person_detail(db, tid, u, full=True)


class RevisionIn(BaseModel):
    effective_from: dt.date
    annual_ctc: float = Field(..., ge=0, le=1_000_000_000)
    lines: dict[str, float] = Field(..., min_length=1)
    reason: str | None = Field(None, max_length=255)


@router.post("/people/{user_id}/revisions", status_code=201)
async def add_revision(user_id: int, data: RevisionIn,
                       ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    _not_own_pay(ctx, user_id)
    u = await _person(db, tid, user_id)
    fixed = {c["code"] for c in await svc.components_for(db, tid) if c["calc"] == "fixed"}
    lines = {}
    for code, amount in data.lines.items():
        code = code.strip().upper()
        if code not in fixed:
            raise HTTPException(422, f"{code} is not a fixed component — add it under Pay components first.")
        if amount < 0:
            raise HTTPException(422, "Amounts cannot be negative.")
        if amount:
            lines[code] = round(amount, 2)
    if not lines:
        raise HTTPException(422, "A salary structure needs at least one amount.")
    r = SalaryRevision(tenant_id=tid, user_id=u.id, effective_from=data.effective_from,
                       annual_ctc=data.annual_ctc, lines=lines, reason=data.reason, created_by=ctx.user.id)
    db.add(r)
    await db.flush()
    await audit.record(db, action="payroll.salary_revised", target_type="user", target_id=u.id,
                       # No amounts: an Org Admin reads audit entries about their
                       # department's people, and salaries are not theirs to see.
                       details={"name": u.name, "effective_from": data.effective_from.isoformat()},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _person_detail(db, tid, u, full=True)


# ─── months ──────────────────────────────────────────────────────────────────

class RunIn(BaseModel):
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$")


@router.get("/runs")
async def list_runs(ctx: SecurityContext = Depends(require_permission("payroll.view")),
                    db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    runs = (await db.execute(select(PayrollRun).where(PayrollRun.tenant_id == tid)
                             .order_by(PayrollRun.period.desc()))).scalars().all()
    return [await svc.run_view(db, r) for r in runs]


async def _run_detail(db, run: PayrollRun, ctx: SecurityContext) -> dict:
    entries = await svc.entries_for(db, run.id)
    view = await svc.run_view(db, run)
    view["entries"] = [svc.entry_view(e) for e in entries]
    view["can_approve"] = (run.status == "submitted" and ctx.permissions.has("payroll.approve")
                           and run.submitted_by != ctx.user.id)
    return view


@router.post("/runs", status_code=201)
async def prepare_run(data: RunIn, ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    try:
        period = calc.parse_period(data.period)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    run = await svc.prepare(db, tid, period, ctx.user)
    await audit.record(db, action="payroll.run_prepared", target_type="payroll_run", target_id=run.id,
                       details={"period": data.period, "people": (run.totals or {}).get("people")},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _run_detail(db, run, ctx)


@router.get("/runs/{run_id}")
async def get_run(run_id: int, ctx: SecurityContext = Depends(require_permission("payroll.view")),
                  db: AsyncSession = Depends(get_db)):
    run = await svc.get_run(db, require_organisation(ctx), run_id)
    return await _run_detail(db, run, ctx)


@router.post("/runs/{run_id}/recompute")
async def recompute_run(run_id: int, ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                        db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    await svc.prepare(db, tid, run.period, ctx.user, run=run)
    await audit.record(db, action="payroll.run_prepared", target_type="payroll_run", target_id=run.id,
                       details={"period": run.period.strftime("%Y-%m"), "recompute": True},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _run_detail(db, run, ctx)


class Adjustment(BaseModel):
    kind: Literal["earning", "deduction"]
    label: str = Field(..., min_length=1, max_length=60)
    amount: float = Field(..., gt=0, le=100_000_000)


class EntryPatch(BaseModel):
    lop_override: float | None = Field(None, ge=0, le=31)
    clear_override: bool = False
    override_note: str | None = Field(None, max_length=255)
    adjustments: list[Adjustment] | None = Field(None, max_length=20)


@router.patch("/runs/{run_id}/entries/{entry_id}")
async def adjust_entry(run_id: int, entry_id: int, data: EntryPatch,
                       ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    if run.status != "draft":
        raise HTTPException(409, f"This month is {run.status}; payslips can only change in a draft.")
    e = await svc.entry_in_run(db, run, entry_id)
    _not_own_pay(ctx, e.user_id)
    if data.clear_override:
        e.lop_override = None
    elif data.lop_override is not None:
        e.lop_override = data.lop_override
    if data.override_note is not None:
        e.override_note = data.override_note or None
    if data.adjustments is not None:
        e.adjustments = [a.model_dump() for a in data.adjustments]
    await svc.prepare(db, tid, run.period, ctx.user, run=run)
    await audit.record(db, action="payroll.entry_adjusted", target_type="payroll_entry", target_id=e.id,
                       details={"period": run.period.strftime("%Y-%m"),
                                "name": (e.data or {}).get("employee", {}).get("name"),
                                "lop_override": float(e.lop_override) if e.lop_override is not None else None,
                                "adjustments": len(e.adjustments or [])},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _run_detail(db, run, ctx)


@router.post("/runs/{run_id}/submit")
async def submit_run(run_id: int, ctx: SecurityContext = Depends(require_permission("payroll.manage")),
                     db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    svc.submit(run, ctx.user)
    await audit.record(db, action="payroll.run_submitted", target_type="payroll_run", target_id=run.id,
                       details={"period": run.period.strftime("%Y-%m"), "totals": run.totals},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _run_detail(db, run, ctx)


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: int, ctx: SecurityContext = Depends(require_permission("payroll.approve")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    await svc.approve(db, run, ctx.user)
    await audit.record(db, action="payroll.run_approved", target_type="payroll_run", target_id=run.id,
                       details={"period": run.period.strftime("%Y-%m"), "totals": run.totals},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _run_detail(db, run, ctx)


class ReturnIn(BaseModel):
    note: str = Field(..., min_length=3, max_length=500)


@router.post("/runs/{run_id}/return")
async def return_run(run_id: int, data: ReturnIn,
                     ctx: SecurityContext = Depends(require_permission("payroll.view")),
                     db: AsyncSession = Depends(get_db)):
    """The checker sends it back, or the maker withdraws it to fix something."""
    if not (ctx.permissions.has("payroll.approve") or ctx.permissions.has("payroll.manage")):
        raise HTTPException(403, "This action requires the 'payroll.approve' permission.")
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    svc.send_back(run, data.note)
    await audit.record(db, action="payroll.run_returned", target_type="payroll_run", target_id=run.id,
                       details={"period": run.period.strftime("%Y-%m"), "note": data.note},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _run_detail(db, run, ctx)


async def _export_args(db, tid, run):
    entries = [svc.entry_view(e, full=True) for e in await svc.entries_for(db, run.id)]
    return entries, {"organisation": await svc.tenant_name(db, tid),
                         "period_label": calc.period_label(run.period), "status": run.status}


@router.get("/runs/{run_id}/register.csv")
async def register_csv(run_id: int, ctx: SecurityContext = Depends(require_permission("payroll.view")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    entries, meta = await _export_args(db, tid, run)
    await audit.record(db, action="payroll.register_exported", target_type="payroll_run", target_id=run.id,
                       details={"period": run.period.strftime("%Y-%m"), "kind": "register",
                                "status": run.status, "people": len(entries)},
                       **ctx.audit_kwargs())
    await db.commit()
    return _csv(payroll_docs.register_csv(entries, **meta),
                f"payroll-register-{run.period.strftime('%Y-%m')}.csv")


@router.get("/runs/{run_id}/summary.csv")
async def summary_csv(run_id: int, ctx: SecurityContext = Depends(require_permission("payroll.view")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    entries, meta = await _export_args(db, tid, run)
    await audit.record(db, action="payroll.register_exported", target_type="payroll_run", target_id=run.id,
                       details={"period": run.period.strftime("%Y-%m"), "kind": "summary", "status": run.status},
                       **ctx.audit_kwargs())
    await db.commit()
    return _csv(payroll_docs.summary_csv(entries, **meta),
                f"payroll-summary-{run.period.strftime('%Y-%m')}.csv")


async def _payslip(db, tid: int, run: PayrollRun, entry: PayrollEntry) -> Response:
    data = svc.entry_view(entry, full=True)
    pdf = payroll_docs.payslip_pdf(
        data, organisation=await svc.tenant_name(db, tid),
        period_label=calc.period_label(run.period), status=run.status,
    )
    name = _slug(data["employee"].get("employee_code") or data["employee"].get("name"))
    return _pdf(pdf, f"payslip-{run.period.strftime('%Y-%m')}-{name}.pdf")


@router.get("/runs/{run_id}/entries/{entry_id}/payslip.pdf")
async def admin_payslip(run_id: int, entry_id: int,
                        ctx: SecurityContext = Depends(require_permission("payroll.view")),
                        db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    run = await svc.get_run(db, tid, run_id)
    entry = await svc.entry_in_run(db, run, entry_id)
    await audit.record(db, action="payroll.payslip_downloaded", target_type="payroll_entry",
                       target_id=entry.id, details={"period": run.period.strftime("%Y-%m"),
                                                    "name": (entry.data or {}).get("employee", {}).get("name")},
                       **ctx.audit_kwargs())
    await db.commit()
    return await _payslip(db, tid, run, entry)


# ─── expense claims: deciding ────────────────────────────────────────────────

def _claim_view(r: Reimbursement, names: dict[int, str]) -> dict:
    return {
        "id": r.id, "user_id": r.user_id, "name": names.get(r.user_id), "category": r.category,
        "description": r.description, "amount": float(r.amount), "expense_date": r.expense_date.isoformat(),
        "reference": r.reference, "status": r.status, "decided_by": names.get(r.decided_by),
        "decided_at": r.decided_at, "decision_note": r.decision_note, "created_at": r.created_at,
        "paid_in_run": r.payroll_run_id,
    }


async def _claim_scope(db, ctx: SecurityContext, tid: int):
    """Whose claims this admin decides: everyone (payroll.manage or Super
    Admin), or an Org Admin's own department's employees."""
    q = select(User.id).where(User.tenant_id == tid, User.id != ctx.user.id)
    if ctx.permissions.grants_all or ctx.permissions.has("payroll.manage"):
        return q
    if ctx.user.role == "org_admin" and ctx.user.dept_id is not None:
        return q.where(User.dept_id == ctx.user.dept_id, User.role == "employee")
    return None


@router.get("/reimbursements")
async def list_claims(status: Literal["pending", "approved", "rejected", "paid", "all"] = "pending",
                      ctx: SecurityContext = Depends(require_permission("reimbursement.approve")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    scope = await _claim_scope(db, ctx, tid)
    if scope is None:
        return []
    q = select(Reimbursement).where(Reimbursement.tenant_id == tid, Reimbursement.user_id.in_(scope))
    if status != "all":
        q = q.where(Reimbursement.status == status)
    rows = (await db.execute(q.order_by(Reimbursement.created_at.desc()).limit(500))).scalars().all()
    who = await svc.names(db, [r.user_id for r in rows] + [r.decided_by for r in rows])
    return [_claim_view(r, who) for r in rows]


class DecideIn(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=255)


@router.post("/reimbursements/{claim_id}/decide")
async def decide_claim(claim_id: int, data: DecideIn,
                       ctx: SecurityContext = Depends(require_permission("reimbursement.approve")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    scope = await _claim_scope(db, ctx, tid)
    r = None
    if scope is not None:
        r = (await db.execute(select(Reimbursement).where(
            Reimbursement.id == claim_id, Reimbursement.tenant_id == tid,
            Reimbursement.user_id.in_(scope)))).scalars().first()
    if not r:
        raise HTTPException(404, "Claim not found among the people you approve for.")
    if r.status != "pending":
        raise HTTPException(409, f"This claim is already {r.status}.")
    if not data.approve and not (data.note or "").strip():
        raise HTTPException(422, "Say why the claim is rejected — the employee sees this note.")
    r.status = "approved" if data.approve else "rejected"
    r.decided_by = ctx.user.id
    r.decided_at = clock_service.now_utc()
    r.decision_note = (data.note or "").strip() or None
    details = {"amount": float(r.amount), "category": r.category, "employee_id": r.user_id}
    if data.approve:
        await audit.record(db, action="reimbursement.approved", target_type="reimbursement", target_id=r.id,
                           details=details, **ctx.audit_kwargs())
    else:
        await audit.record(db, action="reimbursement.rejected", target_type="reimbursement", target_id=r.id,
                           details={**details, "note": r.decision_note}, **ctx.audit_kwargs())
    await db.commit()
    who = await svc.names(db, [r.user_id, r.decided_by])
    return _claim_view(r, who)


# ─── self-service ────────────────────────────────────────────────────────────

@router.get("/me")
async def my_pay(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    return await _person_detail(db, tid, ctx.user, full=False)


@router.get("/me/payslips")
async def my_payslips(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    """Closed months only — a draft is not a payslip yet."""
    tid = _own_tenant(ctx)
    rows = (await db.execute(
        select(PayrollEntry, PayrollRun).join(PayrollRun, PayrollRun.id == PayrollEntry.run_id)
        .where(PayrollEntry.user_id == ctx.user.id, PayrollRun.tenant_id == tid,
               PayrollRun.status == "closed")
        .order_by(PayrollRun.period.desc())
    )).all()
    return [{
        "id": e.id, "period": run.period.strftime("%Y-%m"), "label": calc.period_label(run.period),
        "gross": float(e.gross), "net_pay": float(e.net_pay),
        "total_deductions": (e.data or {}).get("total_deductions"),
        "paid_days": (e.data or {}).get("days", {}).get("paid_days"),
        "lop_days": (e.data or {}).get("days", {}).get("lop_days"),
    } for e, run in rows]


@router.get("/me/payslips/{entry_id}/payslip.pdf")
async def my_payslip_pdf(entry_id: int, ctx: SecurityContext = Depends(get_security_context),
                         db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    row = (await db.execute(
        select(PayrollEntry, PayrollRun).join(PayrollRun, PayrollRun.id == PayrollEntry.run_id)
        .where(PayrollEntry.id == entry_id, PayrollEntry.user_id == ctx.user.id,
               PayrollRun.tenant_id == tid, PayrollRun.status == "closed")
    )).first()
    if not row:
        raise HTTPException(404, "Payslip not found.")
    entry, run = row
    return await _payslip(db, tid, run, entry)


@router.get("/me/reimbursements")
async def my_claims(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    rows = (await db.execute(select(Reimbursement).where(
        Reimbursement.tenant_id == tid, Reimbursement.user_id == ctx.user.id)
        .order_by(Reimbursement.created_at.desc()).limit(200))).scalars().all()
    who = await svc.names(db, [ctx.user.id] + [r.decided_by for r in rows])
    return [_claim_view(r, who) for r in rows]


class ClaimIn(BaseModel):
    category: str = Field(..., min_length=2, max_length=40)
    description: str | None = Field(None, max_length=500)
    amount: float = Field(..., gt=0, le=1_000_000)
    expense_date: dt.date
    reference: str | None = Field(None, max_length=120)


@router.post("/me/reimbursements", status_code=201)
async def submit_claim(data: ClaimIn, ctx: SecurityContext = Depends(get_security_context),
                       db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    if data.expense_date > clock_service.local_today():
        raise HTTPException(422, "The expense date cannot be in the future.")
    r = Reimbursement(tenant_id=tid, user_id=ctx.user.id, category=data.category.strip(),
                      description=(data.description or "").strip() or None, amount=round(data.amount, 2),
                      expense_date=data.expense_date, reference=(data.reference or "").strip() or None)
    db.add(r)
    await db.flush()
    await audit.record(db, action="reimbursement.submitted", target_type="reimbursement", target_id=r.id,
                       details={"amount": float(r.amount), "category": r.category}, **ctx.audit_kwargs())
    await db.commit()
    return _claim_view(r, {ctx.user.id: ctx.user.name})


@router.delete("/me/reimbursements/{claim_id}", status_code=204)
async def withdraw_claim(claim_id: int, ctx: SecurityContext = Depends(get_security_context),
                         db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    r = (await db.execute(select(Reimbursement).where(
        Reimbursement.id == claim_id, Reimbursement.tenant_id == tid,
        Reimbursement.user_id == ctx.user.id))).scalars().first()
    if not r:
        raise HTTPException(404, "Claim not found.")
    if r.status != "pending":
        raise HTTPException(409, f"Only a pending claim can be withdrawn; this one is {r.status}.")
    await audit.record(db, action="reimbursement.withdrawn", target_type="reimbursement", target_id=r.id,
                       details={"amount": float(r.amount), "category": r.category}, **ctx.audit_kwargs())
    await db.delete(r)
    await db.commit()
    return Response(status_code=204)


@router.get("/periods")
async def open_periods(ctx: SecurityContext = Depends(require_permission("payroll.view")),
                       months: int = Query(12, ge=1, le=36)):
    """Months that can be prepared: this one and the ones before it."""
    today = clock_service.local_today().replace(day=1)
    out, d = [], today
    for _ in range(months):
        out.append({"period": d.strftime("%Y-%m"), "label": calc.period_label(d)})
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return out
