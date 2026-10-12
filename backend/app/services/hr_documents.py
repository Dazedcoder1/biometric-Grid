"""
HR documents: stored files, who a policy is for, who has acknowledged it,
and reminders before things expire.

Files
  Kept in the database (stored_files), 10 MB each. The type is decided from
  the file's first bytes, not from the name or the browser's claim, and only
  PDF, PNG, JPEG, Word (.docx) and plain text are accepted — so an uploaded
  "policy.pdf" that is really an HTML page or a script is refused.

Acknowledgement
  Per version. Publishing a new version of a policy asks everyone in its
  audience again; acknowledging version 2 says nothing about version 3.

Expiry reminders
  A person's documents (visa, contract, certificate…) remind at 30 days, 7
  days and on expiry; a policy's review date reminds HR the same way. Each
  stage is sent once — reminder_stage / last_reminded_on remember it — and a
  renewed document starts over. HR (Tenant Admins and anyone with HR access)
  is told; for a person's own document, so is the person.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging

from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.domain import (
    EmployeeDocument, HrDocument, HrDocumentAck, HrDocumentVersion, StoredFile, User,
)
from app.services import clock_service, notification_service

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024
REMIND_AT = (30, 7, 0)                       # days before expiry
STAFF_ROLES = ("employee", "org_admin")

CATEGORIES = {
    "leave_policy": "Leave policy",
    "attendance_policy": "Attendance policy",
    "handbook": "Employee handbook",
    "policy": "Policy",
    "other": "Other",
}
DOC_TYPES = {
    "id_proof": "ID proof (Aadhaar, PAN, passport)",
    "passport": "Passport",
    "visa": "Visa / work permit",
    "contract": "Employment contract",
    "nda": "NDA",
    "certificate": "Certificate",
    "education": "Education record",
    "medical": "Medical / fitness",
    "background_check": "Background verification",
    "other": "Other",
}


# ─── files ───────────────────────────────────────────────────────────────────

def sniff(data: bytes, name: str) -> str | None:
    """Content type from the bytes themselves."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data.startswith(b"PK\x03\x04") and name.lower().endswith(".docx") and b"word/" in data[:4000]:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if name.lower().endswith((".txt", ".md")):
        try:
            data[:65536].decode("utf-8")
        except UnicodeDecodeError:
            return None
        if b"\x00" not in data[:65536]:
            return "text/plain; charset=utf-8"
    return None


def safe_name(name: str) -> str:
    keep = "".join(c for c in (name or "file") if c.isalnum() or c in " ._-()").strip()
    return keep[:200] or "file"


async def store_upload(db, tenant_id: int, upload: UploadFile, uploaded_by: int | None) -> StoredFile:
    data = await upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Files can be up to 10 MB.")
    if not data:
        raise HTTPException(422, "The file is empty.")
    name = safe_name(upload.filename or "file")
    ctype = sniff(data, name)
    if ctype is None:
        raise HTTPException(415, "Upload a PDF, PNG, JPEG, Word (.docx) or plain-text file.")
    f = StoredFile(tenant_id=tenant_id, file_name=name, content_type=ctype, size=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), data=data, uploaded_by=uploaded_by)
    db.add(f)
    await db.flush()
    return f


# ─── audiences and acknowledgement ──────────────────────────────────────────

def audience_departments(doc: HrDocument) -> list[int] | None:
    a = doc.audience or {}
    depts = a.get("departments") if isinstance(a, dict) else None
    return [int(x) for x in depts] if depts else None


def in_audience(doc: HrDocument, user: User) -> bool:
    if user.tenant_id != doc.tenant_id or user.role not in STAFF_ROLES:
        return False
    depts = audience_departments(doc)
    return depts is None or user.dept_id in depts


async def audience(db, doc: HrDocument) -> list[User]:
    q = select(User).where(User.tenant_id == doc.tenant_id, User.is_active.is_(True),
                           User.role.in_(STAFF_ROLES))
    depts = audience_departments(doc)
    if depts:
        q = q.where(User.dept_id.in_(depts))
    return list((await db.execute(q.order_by(User.name))).scalars().all())


async def current_version(db, doc: HrDocument) -> HrDocumentVersion | None:
    if not doc.current_version:
        return None
    return (await db.execute(select(HrDocumentVersion).where(
        HrDocumentVersion.document_id == doc.id, HrDocumentVersion.version == doc.current_version
    ))).scalars().first()


async def ack_status(db, doc: HrDocument) -> dict:
    """Who in the audience has acknowledged the current version."""
    ver = await current_version(db, doc)
    people = await audience(db, doc)
    acked: dict[int, dt.datetime] = {}
    if ver:
        for a in (await db.execute(select(HrDocumentAck).where(HrDocumentAck.version_id == ver.id))).scalars().all():
            acked[a.user_id] = a.acknowledged_at
    rows = [{"user_id": u.id, "name": u.name, "employee_code": u.employee_code, "dept_id": u.dept_id,
             "acknowledged_at": acked.get(u.id)} for u in people]
    done = sum(1 for r in rows if r["acknowledged_at"])
    return {"version": doc.current_version, "total": len(rows), "acknowledged": done,
            "pending": len(rows) - done, "people": rows}


async def pending_for(db, user: User) -> list[HrDocument]:
    """Published documents this person still has to acknowledge."""
    if user.tenant_id is None or user.role not in STAFF_ROLES:
        return []
    docs = (await db.execute(select(HrDocument).where(
        HrDocument.tenant_id == user.tenant_id, HrDocument.status == "active",
        HrDocument.requires_ack.is_(True), HrDocument.current_version > 0,
    ))).scalars().all()
    out = []
    for d in docs:
        if not in_audience(d, user):
            continue
        ver = await current_version(db, d)
        if ver is None:
            continue
        done = (await db.execute(select(HrDocumentAck.id).where(
            HrDocumentAck.version_id == ver.id, HrDocumentAck.user_id == user.id))).first()
        if not done:
            out.append(d)
    return out


# ─── expiry ──────────────────────────────────────────────────────────────────

def days_left(expires_on: dt.date | None, today: dt.date) -> int | None:
    return None if expires_on is None else (expires_on - today).days


def due_stage(left: int | None, already: int | None) -> int | None:
    """The reminder stage to send now, if any. Stages count down 30 -> 7 -> 0."""
    if left is None:
        return None
    for stage in sorted(REMIND_AT):                    # 0, 7, 30
        if left <= stage:
            if already is None or stage < already:
                return stage
            return None
    return None


def expiry_state(left: int | None) -> str:
    if left is None:
        return "none"
    if left < 0:
        return "expired"
    if left <= 30:
        return "expiring"
    return "valid"


async def hr_recipients(db, tenant_id: int) -> list[int]:
    rows = (await db.execute(select(User.id).where(
        User.tenant_id == tenant_id, User.is_active.is_(True),
        (User.role == "tenant_admin") | (User.is_hr.is_(True)),
    ))).scalars().all()
    return list(rows)


async def send_reminders(db, today: dt.date) -> int:
    """One pass over every organisation. Returns how many reminders went out."""
    sent = 0
    docs = (await db.execute(select(EmployeeDocument).where(EmployeeDocument.expires_on.is_not(None)))).scalars().all()
    for d in docs:
        left = days_left(d.expires_on, today)
        stage = due_stage(left, d.reminder_stage)
        if stage is None:
            continue
        person = (await db.execute(select(User).where(User.id == d.user_id))).scalars().first()
        if not person or not person.is_active:
            d.reminder_stage = stage
            continue
        when = "has expired" if left < 0 else ("expires today" if left == 0 else f"expires in {left} days")
        title = f"{d.title} {when}"
        recipients = set(await hr_recipients(db, d.tenant_id)) | {person.id}
        await notification_service.create_notifications_for_recipients(
            db, tenant_id=d.tenant_id, actor_id=None, recipient_ids=sorted(recipients),
            event_type="document_expiry", title=title,
            message=f"{person.name}'s {d.title} {when} ({d.expires_on.isoformat()}). Upload the renewed document.",
            entity_type="employee_document", entity_id=d.id, entity_name=d.title,
        )
        d.reminder_stage = stage
        sent += 1

    policies = (await db.execute(select(HrDocument).where(
        HrDocument.review_by.is_not(None), HrDocument.status == "active"))).scalars().all()
    for p in policies:
        left = days_left(p.review_by, today)
        # The stage already sent is the one that was due on the day we last
        # reminded. Moving the review date clears last_reminded_on (routes).
        sent_stage = (due_stage(days_left(p.review_by, p.last_reminded_on), None)
                      if p.last_reminded_on else None)
        stage = due_stage(left, sent_stage)
        if stage is None:
            continue
        when = "is overdue for review" if left < 0 else f"is due for review in {left} days" if left else "is due for review today"
        await notification_service.create_notifications_for_recipients(
            db, tenant_id=p.tenant_id, actor_id=None, recipient_ids=await hr_recipients(db, p.tenant_id),
            event_type="policy_review", title=f"{p.title} {when}",
            message=f"Review date {p.review_by.isoformat()}. Publish a new version or move the review date.",
            entity_type="hr_document", entity_id=p.id, entity_name=p.title,
        )
        p.last_reminded_on = today
        sent += 1
    return sent


async def reminder_loop(interval_seconds: int = 6 * 3600) -> None:
    """Started from the app's lifespan. A dead loop means late reminders, nothing worse."""
    logger.info("HR document expiry reminders started (every %ss).", interval_seconds)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                n = await send_reminders(db, clock_service.local_today())
                await db.commit()
                if n:
                    logger.info("Sent %s document expiry reminder(s).", n)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            logger.error("Document reminder pass failed: %s", exc)
        await asyncio.sleep(interval_seconds)
