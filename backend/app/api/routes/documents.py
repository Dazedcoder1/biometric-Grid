"""
HR documents and letters — /api/documents.

Letterhead and templates (documents.manage to change, documents.view to read)
    /letterhead                          GET, PUT
    /fields                              placeholders a template can use
    /templates                           list, POST
    /templates/starters                  POST: add the starter templates not yet present
    /templates/{id}                      PUT: save a new version of the wording
    /templates/{id}/versions             every saved wording

Letters
    /letters                             list (filters), POST: create a draft
    /letters/prepare                     POST: what a template needs for one person
    /letters/{id}                        GET (logged), PUT (draft only), DELETE (draft only)
    /letters/{id}/issue                  freeze, number, notify the person
    /letters/{id}/revoke                 with a reason
    /letters/{id}/pdf                    download (logged)

Policies and the handbook
    /policies                            list, POST (multipart: file or written text)
    /policies/{id}                       GET with versions and acknowledgement, PUT details
    /policies/{id}/versions              POST: publish a new version — everyone acknowledges again
    /policies/{id}/versions/{v}/file     download (logged)
    /policies/{id}/remind                notify everyone who has not acknowledged

A person's documents (ID proofs, contracts, visas…) with expiry
    /files                               list, POST (multipart)
    /files/expiring                      expired and expiring soon
    /files/{id}                          GET with versions, PUT details
    /files/{id}/versions                 POST: upload a renewal
    /files/{id}/versions/{v}/download    (logged)

Access logs — every view and download above is in the audit log
    /access-log?target_type=&target_id=

Self-service — anyone in an organisation
    /me/letters, /me/letters/{id}/pdf, /me/letters/{id}/acknowledge
    /me/policies, /me/policies/{id}/file, /me/policies/{id}/acknowledge
    /me/files, /me/files/{id}/download

Org Admins see none of this beyond their own: letters carry salaries.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import (
    SecurityContext, get_security_context, require_organisation, require_permission,
)
from app.core import audit
from app.db.session import get_db
from app.models.domain import (
    Department, EmployeeDocument, EmployeeDocumentVersion, EmployeePayProfile, HrDocument,
    HrDocumentAck, HrDocumentVersion, HrSettings, Letter, LetterTemplate, LetterTemplateVersion,
    PayComponent, SalaryRevision, StoredFile, Tenant, User,
)
from app.models.security import AuditLog
from app.services import clock_service, notification_service
from app.services import hr_documents as hd
from app.services import letters as L

router = APIRouter()


# ─── helpers ─────────────────────────────────────────────────────────────────

def _own_tenant(ctx: SecurityContext) -> int:
    if ctx.user.tenant_id is None:
        raise HTTPException(409, "This is for people in an organisation.")
    return ctx.user.tenant_id


async def _person(db, tid: int, user_id: int) -> User:
    u = (await db.execute(select(User).where(User.id == user_id, User.tenant_id == tid))).scalars().first()
    if not u:
        raise HTTPException(404, "Person not found in this organisation.")
    return u


async def _names(db, ids) -> dict[int, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {u.id: u.name for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()}


def _download(data: bytes, name: str, ctype: str) -> Response:
    safe = re.sub(r'[^A-Za-z0-9._() -]+', "_", name)[:150] or "file"
    return Response(data, media_type=ctype, headers={
        "Content-Disposition": f'attachment; filename="{safe}"',
        # Never let a browser sniff an uploaded file into something executable.
        "X-Content-Type-Options": "nosniff",
    })


def _mask(value: str | None) -> str | None:
    if not value:
        return value
    return "•" * max(0, len(value) - 4) + value[-4:]


async def _letterhead(db, tid: int) -> dict:
    s = (await db.execute(select(HrSettings).where(HrSettings.tenant_id == tid))).scalars().first()
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalars().first()
    base = {"company_name": tenant.name if tenant else "", "address": None, "contact_line": None, "cin": None,
            "signatory_name": None, "signatory_title": None, "footer": None, "reference_prefix": None}
    if s:
        for k in base:
            v = getattr(s, k)
            if v:
                base[k] = v
    return base


# ─── letterhead and fields ───────────────────────────────────────────────────

class LetterheadIn(BaseModel):
    company_name: str | None = Field(None, max_length=160)
    address: str | None = Field(None, max_length=1000)
    contact_line: str | None = Field(None, max_length=255)
    cin: str | None = Field(None, max_length=32)
    signatory_name: str | None = Field(None, max_length=120)
    signatory_title: str | None = Field(None, max_length=120)
    footer: str | None = Field(None, max_length=255)
    reference_prefix: str | None = Field(None, max_length=20, pattern=r"^[A-Za-z0-9-]*$")


@router.get("/letterhead")
async def get_letterhead(ctx: SecurityContext = Depends(require_permission("documents.view")),
                         db: AsyncSession = Depends(get_db)):
    return await _letterhead(db, require_organisation(ctx))


@router.put("/letterhead")
async def save_letterhead(data: LetterheadIn, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                          db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    s = (await db.execute(select(HrSettings).where(HrSettings.tenant_id == tid))).scalars().first()
    if s is None:
        s = HrSettings(tenant_id=tid)
        db.add(s)
    for k, v in data.model_dump().items():
        setattr(s, k, (v or "").strip() or None)
    filled = sorted(k for k, v in data.model_dump().items() if v)
    await audit.record(db, action="document.letterhead_updated", target_type="hr_settings", target_id=tid,
                       details={"fields": filled}, **ctx.audit_kwargs())
    await db.commit()
    return await _letterhead(db, tid)


@router.get("/people")
async def people(ctx: SecurityContext = Depends(require_permission("documents.view")),
                 db: AsyncSession = Depends(get_db)):
    """Everyone a letter or document can be for. HR needs this without the Tenant Admin screens."""
    tid = require_organisation(ctx)
    depts = {d.department_id: d.department_name for d in (await db.execute(
        select(Department).where(Department.tenant_id == tid))).scalars().all()}
    rows = (await db.execute(select(User).where(
        User.tenant_id == tid, User.role.in_(("employee", "org_admin"))).order_by(User.name))).scalars().all()
    return [{"id": u.id, "name": u.name, "employee_code": u.employee_code, "role": u.role,
             "department": depts.get(u.dept_id), "dept_id": u.dept_id, "is_active": u.is_active} for u in rows]


@router.get("/departments")
async def departments(ctx: SecurityContext = Depends(require_permission("documents.view")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    rows = (await db.execute(select(Department).where(Department.tenant_id == tid, Department.is_active.is_(True))
                             .order_by(Department.department_name))).scalars().all()
    return [{"id": d.department_id, "name": d.department_name} for d in rows]


@router.get("/fields")
async def template_fields(ctx: SecurityContext = Depends(require_permission("documents.view"))):
    return {
        "auto": [{"name": k, "label": v} for k, v in L.AUTO_FIELDS.items()],
        "manual": [{"name": k, "label": v[0], "type": v[1]} for k, v in L.MANUAL_HINTS.items()],
        "kinds": [{"kind": k, "label": v} for k, v in L.KINDS.items()],
    }


# ─── templates ───────────────────────────────────────────────────────────────

def _template_view(t: LetterTemplate) -> dict:
    used = L.placeholders(t.subject, t.body)
    return {"id": t.id, "kind": t.kind, "kind_label": L.KINDS.get(t.kind, t.kind), "name": t.name,
            "subject": t.subject, "body": t.body, "version": t.version, "active": t.active,
            "updated_at": t.updated_at,
            "fields": [{"name": f, "label": L.field_label(f), "auto": f in L.AUTO_FIELDS,
                        "type": L.field_type(f)} for f in used]}


class TemplateIn(BaseModel):
    kind: Literal["offer", "appointment", "internship", "confirmation", "promotion",
                  "salary_revision", "experience", "relieving", "other"]
    name: str = Field(..., min_length=2, max_length=120)
    subject: str = Field(..., min_length=2, max_length=200)
    body: str = Field(..., min_length=10, max_length=50_000)


class TemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    subject: str | None = Field(None, min_length=2, max_length=200)
    body: str | None = Field(None, min_length=10, max_length=50_000)
    active: bool | None = None
    note: str | None = Field(None, max_length=255)


async def _template(db, tid: int, template_id: int) -> LetterTemplate:
    t = (await db.execute(select(LetterTemplate).where(
        LetterTemplate.id == template_id, LetterTemplate.tenant_id == tid))).scalars().first()
    if not t:
        raise HTTPException(404, "Template not found.")
    return t


@router.get("/templates")
async def list_templates(ctx: SecurityContext = Depends(require_permission("documents.view")),
                         db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    rows = (await db.execute(select(LetterTemplate).where(LetterTemplate.tenant_id == tid)
                             .order_by(LetterTemplate.kind, LetterTemplate.name))).scalars().all()
    return [_template_view(t) for t in rows]


async def _add_template(db, ctx, tid, kind, name, subject, body, note) -> LetterTemplate:
    t = LetterTemplate(tenant_id=tid, kind=kind, name=name, subject=subject, body=body, version=1,
                       updated_by=ctx.user.id)
    db.add(t)
    await db.flush()
    db.add(LetterTemplateVersion(template_id=t.id, version=1, subject=subject, body=body, note=note,
                                 created_by=ctx.user.id))
    return t


@router.post("/templates/starters", status_code=201)
async def add_starters(ctx: SecurityContext = Depends(require_permission("documents.manage")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    have = set((await db.execute(select(LetterTemplate.kind).where(LetterTemplate.tenant_id == tid))).scalars().all())
    added = []
    for kind in L.STARTERS:
        if kind in have:
            continue
        name, subject, body = L.starter(kind)
        await _add_template(db, ctx, tid, kind, name, subject, body, "Starter template")
        added.append(kind)
    if added:
        await audit.record(db, action="document.templates_added", target_type="letter_template",
                           details={"kinds": added, "starter": True}, **ctx.audit_kwargs())
    await db.commit()
    return {"added": added}


@router.post("/templates", status_code=201)
async def create_template(data: TemplateIn, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                          db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    t = await _add_template(db, ctx, tid, data.kind, data.name.strip(), data.subject.strip(), data.body, None)
    await audit.record(db, action="document.templates_added", target_type="letter_template", target_id=t.id,
                       details={"kinds": [data.kind], "name": t.name}, **ctx.audit_kwargs())
    await db.commit()
    return _template_view(t)


@router.put("/templates/{template_id}")
async def update_template(template_id: int, data: TemplateUpdate,
                          ctx: SecurityContext = Depends(require_permission("documents.manage")),
                          db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    t = await _template(db, tid, template_id)
    wording_changed = (data.subject is not None and data.subject != t.subject) or \
                      (data.body is not None and data.body != t.body)
    if data.name is not None:
        t.name = data.name.strip()
    if data.active is not None:
        t.active = data.active
    if wording_changed:
        t.subject = data.subject if data.subject is not None else t.subject
        t.body = data.body if data.body is not None else t.body
        t.version += 1
        db.add(LetterTemplateVersion(template_id=t.id, version=t.version, subject=t.subject, body=t.body,
                                     note=data.note, created_by=ctx.user.id))
    t.updated_by = ctx.user.id
    await audit.record(db, action="document.template_updated", target_type="letter_template", target_id=t.id,
                       details={"name": t.name, "version": t.version, "wording_changed": wording_changed},
                       **ctx.audit_kwargs())
    await db.commit()
    await db.refresh(t)           # updated_at is set by the database
    return _template_view(t)


@router.get("/templates/{template_id}/versions")
async def template_versions(template_id: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                            db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    await _template(db, tid, template_id)
    rows = (await db.execute(select(LetterTemplateVersion).where(LetterTemplateVersion.template_id == template_id)
                             .order_by(LetterTemplateVersion.version.desc()))).scalars().all()
    who = await _names(db, [r.created_by for r in rows])
    return [{"version": r.version, "subject": r.subject, "body": r.body, "note": r.note,
             "created_by": who.get(r.created_by), "created_at": r.created_at} for r in rows]


# ─── letters ─────────────────────────────────────────────────────────────────

async def _values_for(db, tid: int, person: User, letter_date: dt.date, reference_no: str | None) -> dict:
    prof = (await db.execute(select(EmployeePayProfile).where(EmployeePayProfile.user_id == person.id))).scalars().first()
    revs = (await db.execute(select(SalaryRevision).where(
        SalaryRevision.tenant_id == tid, SalaryRevision.user_id == person.id,
        SalaryRevision.effective_from <= letter_date + dt.timedelta(days=366))
        .order_by(SalaryRevision.effective_from.desc(), SalaryRevision.id.desc()))).scalars().all()
    dept = None
    if person.dept_id:
        d = (await db.execute(select(Department).where(Department.department_id == person.dept_id))).scalars().first()
        dept = d.department_name if d else None
    names = {c.code: c.name for c in (await db.execute(select(PayComponent).where(PayComponent.tenant_id == tid))).scalars().all()}
    return L.auto_values(user=person, department=dept, profile=prof,
                         current_rev=revs[0] if revs else None, previous_rev=revs[1] if len(revs) > 1 else None,
                         letterhead=await _letterhead(db, tid), letter_date=letter_date,
                         reference_no=reference_no, component_names=names)


def _not_self(ctx: SecurityContext, user_id: int) -> None:
    if user_id == ctx.user.id:
        raise HTTPException(403, "Letters to yourself have to be prepared by someone else.")


def _letter_view(x: Letter, names: dict[int, str], *, full: bool = True) -> dict:
    out = {
        "id": x.id, "user_id": x.user_id, "employee": names.get(x.user_id), "kind": x.kind,
        "kind_label": L.KINDS.get(x.kind, x.kind), "subject": x.subject, "letter_date": x.letter_date.isoformat(),
        "reference_no": x.reference_no, "status": x.status, "issued_at": x.issued_at,
        "issued_by": names.get(x.issued_by), "acknowledged_at": x.acknowledged_at,
        "revoked_at": x.revoked_at, "revoke_reason": x.revoke_reason, "created_at": x.created_at,
        "template_id": x.template_id, "template_version": x.template_version,
    }
    if full:
        out["body"] = x.body
        out["missing"] = [f for f in L.placeholders(x.subject, x.body)
                          if f not in (L.TABLE_TOKEN, "reference_no")]
    return out


async def _letter(db, tid: int, letter_id: int) -> Letter:
    x = (await db.execute(select(Letter).where(Letter.id == letter_id, Letter.tenant_id == tid))).scalars().first()
    if not x:
        raise HTTPException(404, "Letter not found.")
    return x


@router.get("/letters")
async def list_letters(user_id: int | None = None, status: str | None = None, kind: str | None = None,
                       ctx: SecurityContext = Depends(require_permission("documents.view")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    q = select(Letter).where(Letter.tenant_id == tid)
    if user_id:
        q = q.where(Letter.user_id == user_id)
    if status:
        q = q.where(Letter.status == status)
    if kind:
        q = q.where(Letter.kind == kind)
    rows = (await db.execute(q.order_by(Letter.created_at.desc()).limit(500))).scalars().all()
    names = await _names(db, [r.user_id for r in rows] + [r.issued_by for r in rows])
    return [_letter_view(r, names, full=False) for r in rows]


class PrepareIn(BaseModel):
    template_id: int
    user_id: int
    letter_date: dt.date | None = None


@router.post("/letters/prepare")
async def prepare_letter(data: PrepareIn, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                         db: AsyncSession = Depends(get_db)):
    """What this template needs for this person: filled values and the rest to ask for."""
    tid = require_organisation(ctx)
    _not_self(ctx, data.user_id)
    t = await _template(db, tid, data.template_id)
    person = await _person(db, tid, data.user_id)
    when = data.letter_date or clock_service.local_today()
    values = await _values_for(db, tid, person, when, None)
    used = L.placeholders(t.subject, t.body)
    need = [f for f in used if f not in values and f not in (L.TABLE_TOKEN, "reference_no")]
    return {
        "template": _template_view(t),
        "auto": {f: values[f] for f in used if f in values and f != L.TABLE_TOKEN},
        "needs": [{"name": f, "label": L.field_label(f), "type": L.field_type(f)} for f in need],
        "has_salary_table": L.TABLE_TOKEN in used,
        "salary_table": values.get(L.TABLE_TOKEN),
    }


class LetterIn(BaseModel):
    template_id: int
    user_id: int
    letter_date: dt.date | None = None
    values: dict[str, str] = Field(default_factory=dict)


@router.post("/letters", status_code=201)
async def create_letter(data: LetterIn, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                        db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    _not_self(ctx, data.user_id)
    t = await _template(db, tid, data.template_id)
    person = await _person(db, tid, data.user_id)
    when = data.letter_date or clock_service.local_today()
    auto = await _values_for(db, tid, person, when, None)
    typed = {k: str(v)[:500] for k, v in data.values.items() if k not in L.AUTO_FIELDS and str(v).strip()}
    values = {**auto, **typed}
    subject, _ = L.fill(t.subject, values)
    body, _ = L.fill(t.body, values)
    x = Letter(tenant_id=tid, user_id=person.id, template_id=t.id, template_version=t.version, kind=t.kind,
               subject=subject, body=body, letter_date=when, status="draft", created_by=ctx.user.id,
               fields={**typed, L.TABLE_TOKEN: auto.get(L.TABLE_TOKEN)})
    db.add(x)
    await db.flush()
    await audit.record(db, action="letter.drafted", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "employee_id": person.id, "name": person.name}, **ctx.audit_kwargs())
    await db.commit()
    return _letter_view(x, {person.id: person.name})


@router.get("/letters/{letter_id}")
async def get_letter(letter_id: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                     db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    x = await _letter(db, tid, letter_id)
    await audit.record(db, action="letter.viewed", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "employee_id": x.user_id}, **ctx.audit_kwargs())
    await db.commit()
    return _letter_view(x, await _names(db, [x.user_id, x.issued_by]))


class LetterEdit(BaseModel):
    subject: str | None = Field(None, min_length=2, max_length=200)
    body: str | None = Field(None, min_length=10, max_length=50_000)
    letter_date: dt.date | None = None


@router.put("/letters/{letter_id}")
async def edit_letter(letter_id: int, data: LetterEdit,
                      ctx: SecurityContext = Depends(require_permission("documents.manage")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    x = await _letter(db, tid, letter_id)
    if x.status != "draft":
        raise HTTPException(409, "Only a draft can be edited. Revoke this letter and issue a new one.")
    _not_self(ctx, x.user_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(x, k, v)
    await audit.record(db, action="letter.edited", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "employee_id": x.user_id}, **ctx.audit_kwargs())
    await db.commit()
    return _letter_view(x, await _names(db, [x.user_id]))


@router.delete("/letters/{letter_id}", status_code=204)
async def delete_draft(letter_id: int, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    x = await _letter(db, tid, letter_id)
    if x.status != "draft":
        raise HTTPException(409, "Issued letters are kept. Revoke it instead.")
    await audit.record(db, action="letter.discarded", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "employee_id": x.user_id}, **ctx.audit_kwargs())
    await db.delete(x)
    await db.commit()
    return Response(status_code=204)


async def _next_reference(db, tid: int, kind: str, prefix: str | None, year: int) -> str:
    n = (await db.execute(select(func.count(Letter.id)).where(
        Letter.tenant_id == tid, Letter.reference_no.is_not(None),
        func.extract("year", Letter.letter_date) == year))).scalar() or 0
    head = (prefix or "HR").upper()
    return f"{head}/{kind.upper().replace('_', '-')}/{year}/{n + 1:04d}"


@router.post("/letters/{letter_id}/issue")
async def issue_letter(letter_id: int, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                       db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    x = await _letter(db, tid, letter_id)
    if x.status != "draft":
        raise HTTPException(409, f"This letter is already {x.status}.")
    _not_self(ctx, x.user_id)
    head = await _letterhead(db, tid)
    ref = await _next_reference(db, tid, x.kind, head.get("reference_prefix"), x.letter_date.year)
    x.subject, _ = L.fill(x.subject, {"reference_no": ref})
    x.body, _ = L.fill(x.body, {"reference_no": ref})
    missing = [f for f in L.placeholders(x.subject, x.body) if f != L.TABLE_TOKEN]
    if missing:
        raise HTTPException(422, "Fill in before issuing: " + ", ".join(L.field_label(f) for f in missing))
    if not head.get("company_name") or not head.get("signatory_name"):
        raise HTTPException(422, "Set the company name and signatory under Letterhead first.")
    x.reference_no = ref
    x.letterhead = head
    x.status = "issued"
    x.issued_by = ctx.user.id
    x.issued_at = clock_service.now_utc()
    person = await _person(db, tid, x.user_id)
    await audit.record(db, action="letter.issued", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "reference_no": ref, "employee_id": person.id, "name": person.name},
                       **ctx.audit_kwargs())
    await notification_service.notify_single_user(
        db, tenant_id=tid, actor_id=ctx.user.id, recipient_id=person.id, event_type="letter_issued",
        title=f"New letter: {L.KINDS.get(x.kind, 'Letter')}",
        message=f"{x.subject} ({ref}) is in My Documents.", entity_type="letter", entity_id=x.id,
        entity_name=x.subject,
    )
    await db.commit()
    return _letter_view(x, await _names(db, [x.user_id, x.issued_by]))


class RevokeIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)


@router.post("/letters/{letter_id}/revoke")
async def revoke_letter(letter_id: int, data: RevokeIn,
                        ctx: SecurityContext = Depends(require_permission("documents.manage")),
                        db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    x = await _letter(db, tid, letter_id)
    if x.status != "issued":
        raise HTTPException(409, "Only an issued letter can be revoked.")
    x.status = "revoked"
    x.revoked_by = ctx.user.id
    x.revoked_at = clock_service.now_utc()
    x.revoke_reason = data.reason
    await audit.record(db, action="letter.revoked", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "reference_no": x.reference_no, "reason": data.reason},
                       **ctx.audit_kwargs())
    await notification_service.notify_single_user(
        db, tenant_id=tid, actor_id=ctx.user.id, recipient_id=x.user_id, event_type="letter_revoked",
        title="A letter was withdrawn", message=f"{x.subject} ({x.reference_no}) was withdrawn: {data.reason}",
        entity_type="letter", entity_id=x.id, entity_name=x.subject,
    )
    await db.commit()
    return _letter_view(x, await _names(db, [x.user_id, x.issued_by]))


async def _letter_pdf(db, tid: int, x: Letter) -> Response:
    person = await _person(db, tid, x.user_id)
    prof = (await db.execute(select(EmployeePayProfile).where(EmployeePayProfile.user_id == person.id))).scalars().first()
    head = x.letterhead or await _letterhead(db, tid)
    pdf = L.letter_pdf(
        subject=x.subject, body=x.body, letterhead=head,
        recipient={"name": person.name, "designation": getattr(prof, "designation", None),
                   "employee_code": person.employee_code},
        letter_date=x.letter_date, reference_no=x.reference_no, status=x.status,
        salary_rows=(x.fields or {}).get(L.TABLE_TOKEN),
    )
    name = f"{x.kind}-{(person.employee_code or person.name or 'letter')}-{x.letter_date.isoformat()}.pdf"
    return _download(pdf, name, "application/pdf")


@router.get("/letters/{letter_id}/pdf")
async def letter_pdf(letter_id: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                     db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    x = await _letter(db, tid, letter_id)
    await audit.record(db, action="letter.downloaded", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "status": x.status, "employee_id": x.user_id}, **ctx.audit_kwargs())
    await db.commit()
    return await _letter_pdf(db, tid, x)


# ─── policies and the handbook ───────────────────────────────────────────────

def _depts_from(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        ids = [int(x) for x in json.loads(raw)]
    except (ValueError, TypeError):
        raise HTTPException(422, "departments must be a JSON list of ids.") from None
    return {"departments": ids} if ids else None


async def _policy(db, tid: int, doc_id: int) -> HrDocument:
    d = (await db.execute(select(HrDocument).where(HrDocument.id == doc_id, HrDocument.tenant_id == tid))).scalars().first()
    if not d:
        raise HTTPException(404, "Document not found.")
    return d


async def _publish(db, ctx, doc: HrDocument, file: UploadFile | None, body: str | None, note: str | None) -> HrDocumentVersion:
    if (file is None or not file.filename) and not (body or "").strip():
        raise HTTPException(422, "Attach a file or write the text.")
    stored = await hd.store_upload(db, doc.tenant_id, file, ctx.user.id) if file is not None and file.filename else None
    doc.current_version = (doc.current_version or 0) + 1
    v = HrDocumentVersion(document_id=doc.id, version=doc.current_version, file_id=stored.id if stored else None,
                          body=(body or "").strip() or None, change_note=note, published_by=ctx.user.id)
    db.add(v)
    await db.flush()
    people = await hd.audience(db, doc)
    if people and doc.status == "active":
        await notification_service.create_notifications_for_recipients(
            db, tenant_id=doc.tenant_id, actor_id=ctx.user.id,
            recipient_ids=[u.id for u in people if u.id != ctx.user.id],
            event_type="policy_published",
            title=f"{'Please read and acknowledge: ' if doc.requires_ack else 'New: '}{doc.title}",
            message=(f"Version {v.version} is published." + (f" What changed: {note}" if note else "")),
            entity_type="hr_document", entity_id=doc.id, entity_name=doc.title,
        )
    return v


async def _policy_view(db, d: HrDocument, *, detail: bool = False) -> dict:
    status = await hd.ack_status(db, d)
    ver = await hd.current_version(db, d)
    out = {
        "id": d.id, "category": d.category, "category_label": hd.CATEGORIES.get(d.category, d.category),
        "title": d.title, "description": d.description, "requires_ack": d.requires_ack,
        "departments": hd.audience_departments(d), "review_by": d.review_by.isoformat() if d.review_by else None,
        "review_state": hd.expiry_state(hd.days_left(d.review_by, clock_service.local_today())),
        "status": d.status, "current_version": d.current_version,
        "published_at": ver.published_at if ver else None,
        "acknowledged": status["acknowledged"], "audience": status["total"], "pending": status["pending"],
    }
    if detail:
        vers = (await db.execute(select(HrDocumentVersion).where(HrDocumentVersion.document_id == d.id)
                                 .order_by(HrDocumentVersion.version.desc()))).scalars().all()
        files = {f.id: f for f in (await db.execute(select(StoredFile.id, StoredFile.file_name, StoredFile.size,
                 StoredFile.content_type).where(StoredFile.id.in_([v.file_id for v in vers if v.file_id] or [0])))).all()}
        who = await _names(db, [v.published_by for v in vers])
        counts = dict((await db.execute(select(HrDocumentAck.version_id, func.count(HrDocumentAck.id))
                                        .where(HrDocumentAck.document_id == d.id)
                                        .group_by(HrDocumentAck.version_id))).all())
        out["versions"] = [{
            "version": v.version, "change_note": v.change_note, "published_at": v.published_at,
            "published_by": who.get(v.published_by), "has_text": bool(v.body),
            "file_name": files[v.file_id].file_name if v.file_id in files else None,
            "size": files[v.file_id].size if v.file_id in files else None,
            "acknowledged": counts.get(v.id, 0),
        } for v in vers]
        out["people"] = status["people"]
        out["body"] = ver.body if ver else None
    return out


@router.get("/policies")
async def list_policies(ctx: SecurityContext = Depends(require_permission("documents.view")),
                        db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    rows = (await db.execute(select(HrDocument).where(HrDocument.tenant_id == tid)
                             .order_by(HrDocument.status, HrDocument.category, HrDocument.title))).scalars().all()
    return [await _policy_view(db, d) for d in rows]


@router.post("/policies", status_code=201)
async def create_policy(
    category: str = Form(...), title: str = Form(..., min_length=2, max_length=200),
    description: str | None = Form(None), requires_ack: bool = Form(True),
    departments: str | None = Form(None), review_by: dt.date | None = Form(None),
    change_note: str | None = Form(None), body: str | None = Form(None),
    file: UploadFile | None = File(None),
    ctx: SecurityContext = Depends(require_permission("documents.manage")),
    db: AsyncSession = Depends(get_db),
):
    tid = require_organisation(ctx)
    if category not in hd.CATEGORIES:
        raise HTTPException(422, f"category must be one of: {', '.join(hd.CATEGORIES)}")
    d = HrDocument(tenant_id=tid, category=category, title=title.strip(), description=(description or "").strip() or None,
                   requires_ack=requires_ack, audience=_depts_from(departments), review_by=review_by,
                   created_by=ctx.user.id, current_version=0)
    db.add(d)
    await db.flush()
    v = await _publish(db, ctx, d, file, body, change_note or "First version")
    await audit.record(db, action="policy.published", target_type="hr_document", target_id=d.id,
                       details={"title": d.title, "version": v.version, "category": category}, **ctx.audit_kwargs())
    await db.commit()
    return await _policy_view(db, d, detail=True)


class PolicyEdit(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = Field(None, max_length=5000)
    requires_ack: bool | None = None
    departments: list[int] | None = None
    review_by: dt.date | None = None
    clear_review_by: bool = False
    status: Literal["active", "archived"] | None = None


@router.put("/policies/{doc_id}")
async def edit_policy(doc_id: int, data: PolicyEdit, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    d = await _policy(db, tid, doc_id)
    changes = data.model_dump(exclude_unset=True)
    for k in ("title", "description", "requires_ack", "status"):
        if k in changes and changes[k] is not None:
            setattr(d, k, changes[k])
    if "departments" in changes:
        d.audience = {"departments": data.departments} if data.departments else None
    if data.clear_review_by:
        d.review_by, d.last_reminded_on = None, None
    elif data.review_by is not None and data.review_by != d.review_by:
        d.review_by, d.last_reminded_on = data.review_by, None
    await audit.record(db, action="policy.updated", target_type="hr_document", target_id=d.id,
                       details={"title": d.title, "changed": sorted(changes)}, **ctx.audit_kwargs())
    await db.commit()
    return await _policy_view(db, d, detail=True)


@router.get("/policies/{doc_id}")
async def get_policy(doc_id: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                     db: AsyncSession = Depends(get_db)):
    return await _policy_view(db, await _policy(db, require_organisation(ctx), doc_id), detail=True)


@router.post("/policies/{doc_id}/versions", status_code=201)
async def new_policy_version(
    doc_id: int, change_note: str = Form(..., min_length=3, max_length=255),
    body: str | None = Form(None), file: UploadFile | None = File(None),
    ctx: SecurityContext = Depends(require_permission("documents.manage")),
    db: AsyncSession = Depends(get_db),
):
    tid = require_organisation(ctx)
    d = await _policy(db, tid, doc_id)
    v = await _publish(db, ctx, d, file, body, change_note)
    await audit.record(db, action="policy.published", target_type="hr_document", target_id=d.id,
                       details={"title": d.title, "version": v.version, "note": change_note}, **ctx.audit_kwargs())
    await db.commit()
    return await _policy_view(db, d, detail=True)


async def _version_content(db, d: HrDocument, version: int) -> Response:
    v = (await db.execute(select(HrDocumentVersion).where(
        HrDocumentVersion.document_id == d.id, HrDocumentVersion.version == version))).scalars().first()
    if not v:
        raise HTTPException(404, "Version not found.")
    if v.file_id:
        f = (await db.execute(select(StoredFile).where(StoredFile.id == v.file_id))).scalars().first()
        if f:
            return _download(f.data, f.file_name, f.content_type)
    text = f"{d.title}\nVersion {v.version}\n\n{v.body or ''}\n"
    return _download(text.encode("utf-8"), f"{d.title}-v{v.version}.txt", "text/plain; charset=utf-8")


@router.get("/policies/{doc_id}/versions/{version}/file")
async def policy_file(doc_id: int, version: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                      db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    d = await _policy(db, tid, doc_id)
    await audit.record(db, action="policy.downloaded", target_type="hr_document", target_id=d.id,
                       details={"title": d.title, "version": version}, **ctx.audit_kwargs())
    await db.commit()
    return await _version_content(db, d, version)


@router.post("/policies/{doc_id}/remind")
async def remind_policy(doc_id: int, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                        db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    d = await _policy(db, tid, doc_id)
    if not d.requires_ack or d.status != "active":
        raise HTTPException(409, "This document does not ask for acknowledgement.")
    status = await hd.ack_status(db, d)
    pending = [p["user_id"] for p in status["people"] if not p["acknowledged_at"]]
    if pending:
        await notification_service.create_notifications_for_recipients(
            db, tenant_id=tid, actor_id=ctx.user.id, recipient_ids=pending, event_type="policy_reminder",
            title=f"Reminder: please acknowledge {d.title}",
            message=f"Version {d.current_version} is waiting for your acknowledgement in My Documents.",
            entity_type="hr_document", entity_id=d.id, entity_name=d.title,
        )
    await audit.record(db, action="policy.reminded", target_type="hr_document", target_id=d.id,
                       details={"title": d.title, "people": len(pending)}, **ctx.audit_kwargs())
    await db.commit()
    return {"reminded": len(pending)}


# ─── a person's documents ────────────────────────────────────────────────────

def _file_view(d: EmployeeDocument, names: dict[int, str], *, full_number: bool, today: dt.date) -> dict:
    left = hd.days_left(d.expires_on, today)
    return {
        "id": d.id, "user_id": d.user_id, "employee": names.get(d.user_id), "doc_type": d.doc_type,
        "doc_type_label": hd.DOC_TYPES.get(d.doc_type, d.doc_type), "title": d.title,
        "number": d.number if full_number else _mask(d.number),
        "issued_on": d.issued_on.isoformat() if d.issued_on else None,
        "expires_on": d.expires_on.isoformat() if d.expires_on else None,
        "days_left": left, "expiry_state": hd.expiry_state(left), "version": d.current_version,
        "notes": d.notes, "uploaded_by": names.get(d.uploaded_by), "updated_at": d.updated_at,
        "has_file": bool(d.file_id),
    }


async def _emp_doc(db, tid: int, doc_id: int) -> EmployeeDocument:
    d = (await db.execute(select(EmployeeDocument).where(
        EmployeeDocument.id == doc_id, EmployeeDocument.tenant_id == tid))).scalars().first()
    if not d:
        raise HTTPException(404, "Document not found.")
    return d


@router.get("/files")
async def list_files(user_id: int | None = None, ctx: SecurityContext = Depends(require_permission("documents.view")),
                     db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    q = select(EmployeeDocument).where(EmployeeDocument.tenant_id == tid)
    if user_id:
        q = q.where(EmployeeDocument.user_id == user_id)
    rows = (await db.execute(q.order_by(EmployeeDocument.expires_on.asc().nulls_last(),
                                        EmployeeDocument.title).limit(1000))).scalars().all()
    names = await _names(db, [r.user_id for r in rows] + [r.uploaded_by for r in rows])
    full = ctx.permissions.has("documents.manage")
    today = clock_service.local_today()
    return [_file_view(r, names, full_number=full, today=today) for r in rows]


@router.get("/files/expiring")
async def expiring_files(days: int = Query(60, ge=1, le=365),
                         ctx: SecurityContext = Depends(require_permission("documents.view")),
                         db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    today = clock_service.local_today()
    rows = (await db.execute(select(EmployeeDocument).where(
        EmployeeDocument.tenant_id == tid, EmployeeDocument.expires_on.is_not(None),
        EmployeeDocument.expires_on <= today + dt.timedelta(days=days)
    ).order_by(EmployeeDocument.expires_on))).scalars().all()
    names = await _names(db, [r.user_id for r in rows] + [r.uploaded_by for r in rows])
    policies = (await db.execute(select(HrDocument).where(
        HrDocument.tenant_id == tid, HrDocument.status == "active", HrDocument.review_by.is_not(None),
        HrDocument.review_by <= today + dt.timedelta(days=days)))).scalars().all()
    return {
        "documents": [_file_view(r, names, full_number=False, today=today) for r in rows],
        "policies": [{"id": p.id, "title": p.title, "review_by": p.review_by.isoformat(),
                      "days_left": hd.days_left(p.review_by, today),
                      "state": hd.expiry_state(hd.days_left(p.review_by, today))} for p in policies],
    }


@router.post("/files", status_code=201)
async def add_file(
    user_id: int = Form(...), doc_type: str = Form(...), title: str = Form(..., min_length=2, max_length=200),
    number: str | None = Form(None), issued_on: dt.date | None = Form(None),
    expires_on: dt.date | None = Form(None), notes: str | None = Form(None),
    file: UploadFile = File(...),
    ctx: SecurityContext = Depends(require_permission("documents.manage")),
    db: AsyncSession = Depends(get_db),
):
    tid = require_organisation(ctx)
    if doc_type not in hd.DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of: {', '.join(hd.DOC_TYPES)}")
    person = await _person(db, tid, user_id)
    stored = await hd.store_upload(db, tid, file, ctx.user.id)
    d = EmployeeDocument(tenant_id=tid, user_id=person.id, doc_type=doc_type, title=title.strip(),
                         number=(number or "").strip()[:80] or None, issued_on=issued_on, expires_on=expires_on,
                         notes=(notes or "").strip()[:500] or None, file_id=stored.id, current_version=1,
                         uploaded_by=ctx.user.id)
    db.add(d)
    await db.flush()
    db.add(EmployeeDocumentVersion(document_id=d.id, version=1, file_id=stored.id, number=d.number,
                                   issued_on=issued_on, expires_on=expires_on, note="First upload",
                                   created_by=ctx.user.id))
    await audit.record(db, action="document.filed", target_type="employee_document", target_id=d.id,
                       details={"employee_id": person.id, "name": person.name, "doc_type": doc_type,
                                "expires_on": expires_on.isoformat() if expires_on else None},
                       **ctx.audit_kwargs())
    await db.commit()
    return _file_view(d, {person.id: person.name, ctx.user.id: ctx.user.name}, full_number=True,
                      today=clock_service.local_today())


@router.post("/files/{doc_id}/versions", status_code=201)
async def renew_file(
    doc_id: int, file: UploadFile = File(...), number: str | None = Form(None),
    issued_on: dt.date | None = Form(None), expires_on: dt.date | None = Form(None),
    note: str | None = Form(None),
    ctx: SecurityContext = Depends(require_permission("documents.manage")),
    db: AsyncSession = Depends(get_db),
):
    tid = require_organisation(ctx)
    d = await _emp_doc(db, tid, doc_id)
    stored = await hd.store_upload(db, tid, file, ctx.user.id)
    d.current_version += 1
    d.file_id = stored.id
    if number is not None:
        d.number = number.strip()[:80] or None
    d.issued_on = issued_on or d.issued_on
    d.expires_on = expires_on
    d.reminder_stage = None                # a renewed document is reminded afresh
    db.add(EmployeeDocumentVersion(document_id=d.id, version=d.current_version, file_id=stored.id,
                                   number=d.number, issued_on=d.issued_on, expires_on=expires_on,
                                   note=(note or "").strip()[:255] or None, created_by=ctx.user.id))
    await audit.record(db, action="document.renewed", target_type="employee_document", target_id=d.id,
                       details={"employee_id": d.user_id, "version": d.current_version,
                                "expires_on": expires_on.isoformat() if expires_on else None},
                       **ctx.audit_kwargs())
    await db.commit()
    await db.refresh(d)
    return _file_view(d, await _names(db, [d.user_id, d.uploaded_by]), full_number=True,
                      today=clock_service.local_today())


class FileEdit(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=200)
    notes: str | None = Field(None, max_length=500)
    doc_type: str | None = None


@router.put("/files/{doc_id}")
async def edit_file(doc_id: int, data: FileEdit, ctx: SecurityContext = Depends(require_permission("documents.manage")),
                    db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    d = await _emp_doc(db, tid, doc_id)
    if data.doc_type is not None and data.doc_type not in hd.DOC_TYPES:
        raise HTTPException(422, "Unknown document type.")
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(d, k, v)
    await audit.record(db, action="document.updated", target_type="employee_document", target_id=d.id,
                       details={"employee_id": d.user_id}, **ctx.audit_kwargs())
    await db.commit()
    await db.refresh(d)
    return _file_view(d, await _names(db, [d.user_id, d.uploaded_by]), full_number=True,
                      today=clock_service.local_today())


async def _file_versions(db, d: EmployeeDocument) -> list[dict]:
    vers = (await db.execute(select(EmployeeDocumentVersion).where(EmployeeDocumentVersion.document_id == d.id)
                             .order_by(EmployeeDocumentVersion.version.desc()))).scalars().all()
    who = await _names(db, [v.created_by for v in vers])
    files = {r.id: r for r in (await db.execute(select(StoredFile.id, StoredFile.file_name, StoredFile.size)
             .where(StoredFile.id.in_([v.file_id for v in vers if v.file_id] or [0])))).all()}
    return [{"version": v.version, "note": v.note, "created_at": v.created_at, "created_by": who.get(v.created_by),
             "issued_on": v.issued_on.isoformat() if v.issued_on else None,
             "expires_on": v.expires_on.isoformat() if v.expires_on else None,
             "file_name": files[v.file_id].file_name if v.file_id in files else None,
             "size": files[v.file_id].size if v.file_id in files else None} for v in vers]


@router.get("/files/{doc_id}")
async def get_file(doc_id: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                   db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    d = await _emp_doc(db, tid, doc_id)
    out = _file_view(d, await _names(db, [d.user_id, d.uploaded_by]),
                     full_number=ctx.permissions.has("documents.manage"), today=clock_service.local_today())
    out["versions"] = await _file_versions(db, d)
    return out


async def _file_version_download(db, d: EmployeeDocument, version: int) -> Response:
    v = (await db.execute(select(EmployeeDocumentVersion).where(
        EmployeeDocumentVersion.document_id == d.id, EmployeeDocumentVersion.version == version))).scalars().first()
    if not v or not v.file_id:
        raise HTTPException(404, "Version not found.")
    f = (await db.execute(select(StoredFile).where(StoredFile.id == v.file_id))).scalars().first()
    if not f:
        raise HTTPException(404, "File not found.")
    return _download(f.data, f.file_name, f.content_type)


@router.get("/files/{doc_id}/versions/{version}/download")
async def download_file(doc_id: int, version: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                        db: AsyncSession = Depends(get_db)):
    tid = require_organisation(ctx)
    d = await _emp_doc(db, tid, doc_id)
    await audit.record(db, action="document.downloaded", target_type="employee_document", target_id=d.id,
                       details={"employee_id": d.user_id, "version": version, "title": d.title}, **ctx.audit_kwargs())
    await db.commit()
    return await _file_version_download(db, d, version)


# ─── access logs ─────────────────────────────────────────────────────────────

@router.get("/access-log")
async def access_log(target_type: Literal["letter", "hr_document", "employee_document", "letter_template"],
                     target_id: int, ctx: SecurityContext = Depends(require_permission("documents.view")),
                     db: AsyncSession = Depends(get_db)):
    """Everything that happened to one letter or document: created, viewed, downloaded, acknowledged."""
    tid = require_organisation(ctx)
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.tenant_id == tid, AuditLog.target_type == target_type, AuditLog.target_id == str(target_id)
    ).order_by(AuditLog.seq.desc()).limit(500))).scalars().all()
    who = await _names(db, [r.actor_id for r in rows])
    return [{"seq": r.seq, "occurred_at": r.occurred_at, "action": r.action, "result": r.result,
             "actor": who.get(r.actor_id) or r.actor_role, "source_ip": r.source_ip,
             "details": r.details} for r in rows]


# ─── self-service ────────────────────────────────────────────────────────────

@router.get("/me/letters")
async def my_letters(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    rows = (await db.execute(select(Letter).where(
        Letter.tenant_id == tid, Letter.user_id == ctx.user.id, Letter.status.in_(("issued", "revoked")))
        .order_by(Letter.letter_date.desc(), Letter.id.desc()))).scalars().all()
    names = await _names(db, [r.issued_by for r in rows])
    return [_letter_view(r, names, full=False) for r in rows]


async def _my_letter(db, tid: int, ctx, letter_id: int) -> Letter:
    x = (await db.execute(select(Letter).where(
        Letter.id == letter_id, Letter.tenant_id == tid, Letter.user_id == ctx.user.id,
        Letter.status.in_(("issued", "revoked"))))).scalars().first()
    if not x:
        raise HTTPException(404, "Letter not found.")
    return x


@router.get("/me/letters/{letter_id}/pdf")
async def my_letter_pdf(letter_id: int, ctx: SecurityContext = Depends(get_security_context),
                        db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    x = await _my_letter(db, tid, ctx, letter_id)
    await audit.record(db, action="letter.downloaded", target_type="letter", target_id=x.id,
                       details={"kind": x.kind, "by": "recipient"}, **ctx.audit_kwargs())
    await db.commit()
    return await _letter_pdf(db, tid, x)


@router.post("/me/letters/{letter_id}/acknowledge")
async def acknowledge_letter(letter_id: int, ctx: SecurityContext = Depends(get_security_context),
                             db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    x = await _my_letter(db, tid, ctx, letter_id)
    if x.status != "issued":
        raise HTTPException(409, "This letter was withdrawn.")
    if x.acknowledged_at is None:
        x.acknowledged_at = clock_service.now_utc()
        await audit.record(db, action="letter.acknowledged", target_type="letter", target_id=x.id,
                           details={"kind": x.kind, "reference_no": x.reference_no}, **ctx.audit_kwargs())
        await db.commit()
    return {"acknowledged_at": x.acknowledged_at}


@router.get("/me/policies")
async def my_policies(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    docs = (await db.execute(select(HrDocument).where(
        HrDocument.tenant_id == tid, HrDocument.status == "active", HrDocument.current_version > 0)
        .order_by(HrDocument.category, HrDocument.title))).scalars().all()
    out = []
    for d in docs:
        if not hd.in_audience(d, ctx.user):
            continue
        ver = await hd.current_version(db, d)
        ack = None
        if ver:
            ack = (await db.execute(select(HrDocumentAck.acknowledged_at).where(
                HrDocumentAck.version_id == ver.id, HrDocumentAck.user_id == ctx.user.id))).scalar()
        out.append({"id": d.id, "title": d.title, "category": d.category,
                    "category_label": hd.CATEGORIES.get(d.category, d.category), "description": d.description,
                    "version": d.current_version, "published_at": ver.published_at if ver else None,
                    "change_note": ver.change_note if ver else None, "requires_ack": d.requires_ack,
                    "acknowledged_at": ack, "body": ver.body if ver else None,
                    "has_file": bool(ver and ver.file_id)})
    return out


async def _my_policy(db, ctx, tid: int, doc_id: int) -> HrDocument:
    d = await _policy(db, tid, doc_id)
    if d.status != "active" or not hd.in_audience(d, ctx.user):
        raise HTTPException(404, "Document not found.")
    return d


@router.get("/me/policies/{doc_id}/file")
async def my_policy_file(doc_id: int, ctx: SecurityContext = Depends(get_security_context),
                         db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    d = await _my_policy(db, ctx, tid, doc_id)
    await audit.record(db, action="policy.downloaded", target_type="hr_document", target_id=d.id,
                       details={"title": d.title, "version": d.current_version, "by": "reader"}, **ctx.audit_kwargs())
    await db.commit()
    return await _version_content(db, d, d.current_version)


@router.post("/me/policies/{doc_id}/acknowledge")
async def acknowledge_policy(doc_id: int, request: Request, ctx: SecurityContext = Depends(get_security_context),
                             db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    d = await _my_policy(db, ctx, tid, doc_id)
    ver = await hd.current_version(db, d)
    if not ver:
        raise HTTPException(409, "Nothing published yet.")
    existing = (await db.execute(select(HrDocumentAck).where(
        HrDocumentAck.version_id == ver.id, HrDocumentAck.user_id == ctx.user.id))).scalars().first()
    if existing:
        return {"version": ver.version, "acknowledged_at": existing.acknowledged_at}
    a = HrDocumentAck(document_id=d.id, version_id=ver.id, user_id=ctx.user.id, source_ip=ctx.source_ip)
    db.add(a)
    await audit.record(db, action="policy.acknowledged", target_type="hr_document", target_id=d.id,
                       details={"title": d.title, "version": ver.version}, **ctx.audit_kwargs())
    await db.commit()
    return {"version": ver.version, "acknowledged_at": a.acknowledged_at}


@router.get("/me/pending")
async def my_pending(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    """For the dashboard banner: what is waiting for me."""
    if ctx.user.tenant_id is None:
        return {"policies": [], "letters": 0}
    docs = await hd.pending_for(db, ctx.user)
    letters = (await db.execute(select(func.count(Letter.id)).where(
        Letter.user_id == ctx.user.id, Letter.status == "issued", Letter.acknowledged_at.is_(None)))).scalar() or 0
    return {"policies": [{"id": d.id, "title": d.title} for d in docs], "letters": letters}


@router.get("/me/files")
async def my_files(ctx: SecurityContext = Depends(get_security_context), db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    rows = (await db.execute(select(EmployeeDocument).where(
        EmployeeDocument.tenant_id == tid, EmployeeDocument.user_id == ctx.user.id)
        .order_by(EmployeeDocument.title))).scalars().all()
    names = await _names(db, [ctx.user.id] + [r.uploaded_by for r in rows])
    return [_file_view(r, names, full_number=True, today=clock_service.local_today()) for r in rows]


@router.get("/me/files/{doc_id}/download")
async def my_file_download(doc_id: int, ctx: SecurityContext = Depends(get_security_context),
                           db: AsyncSession = Depends(get_db)):
    tid = _own_tenant(ctx)
    d = await _emp_doc(db, tid, doc_id)
    if d.user_id != ctx.user.id:
        raise HTTPException(404, "Document not found.")
    await audit.record(db, action="document.downloaded", target_type="employee_document", target_id=d.id,
                       details={"version": d.current_version, "by": "owner"}, **ctx.audit_kwargs())
    await db.commit()
    return await _file_version_download(db, d, d.current_version)
