"""
Resetting someone's sign-in password.

Nobody can read a sign-in password — they are stored as bcrypt hashes, which
go one way only. When an employee is locked out, or leaves and their accounts
need handing over, the honest answer to "what is their password" is: give
them a new one. That is what this does.

It replaces /api/auth/set-password, which let ANY Org Admin set ANY user's
password in ANY organisation, a Super Admin's included — an Org Admin could
take over the platform in one request. Scope here comes from
oversight_service, the same rule the vault oversight routes use:

    Super Admin   ->  everyone in the organisation they are working in,
                     Tenant Admins included
    Tenant Admin  ->  Org Admins and Employees in their organisation
    Org Admin     ->  Employees in their own department

What a reset does, all in one transaction:

  * sets a temporary password, generated unless one is supplied;
  * marks the account must_change_password, so the person has to choose their
    own before they can do anything else (dependencies.get_current_user);
  * signs them out everywhere — refresh tokens revoked, step-up assertions
    revoked — so a session opened with the old password does not survive;
  * records it in the audit log (never the password) and notifies the person.

The temporary password is returned once, in this response, and stored nowhere
readable.
"""

from __future__ import annotations

import re
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import SecurityContext, require_organisation, require_permission
from app.core import audit, mfa
from app.core.security import hash_password
from app.db.session import get_db
from app.models.domain import User
from app.services import notification_service
from app.services import oversight_service as oversight

router = APIRouter()


def password_problem(pw: str) -> str | None:
    """The app's sign-in password rule, in one place."""
    if len(pw) < 8:
        return "must be at least 8 characters"
    if not re.search(r"[A-Z]", pw):
        return "must contain an uppercase letter"
    if not re.search(r"[a-z]", pw):
        return "must contain a lowercase letter"
    if not re.search(r"[0-9]", pw):
        return "must contain a number"
    return None


def generate_temporary_password() -> str:
    """
    14 characters that satisfy the rule and survive being read aloud or typed
    from a screen: no 0/O, 1/l/I.
    """
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    lower = "abcdefghijkmnpqrstuvwxyz"
    digits = "23456789"
    alphabet = upper + lower + digits
    while True:
        chars = [secrets.choice(upper), secrets.choice(lower), secrets.choice(digits)]
        chars += [secrets.choice(alphabet) for _ in range(11)]
        # SystemRandom shuffle, so the guaranteed classes are not always first.
        secrets.SystemRandom().shuffle(chars)
        pw = "".join(chars)
        if not password_problem(pw):
            return pw


class ResetIn(BaseModel):
    # Optional: most admins should let the server generate one.
    temporary_password: str | None = Field(None, max_length=128)

    @field_validator("temporary_password")
    @classmethod
    def _policy(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        problem = password_problem(v)
        if problem:
            raise ValueError(f"Password {problem}")
        return v


@router.post("/accounts/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    data: ResetIn | None = None,
    ctx: SecurityContext = Depends(require_permission("user.password_reset")),
    db: AsyncSession = Depends(get_db),
):
    org = require_organisation(ctx)
    if user_id == ctx.user.id:
        raise HTTPException(400, "To change your own password, use Change password.")

    person = await oversight.get_overseeable(db, ctx.user, user_id, org)

    temporary = (data.temporary_password if data else None) or generate_temporary_password()
    generated = not (data and data.temporary_password)

    person.password_hash = hash_password(temporary)
    person.must_change_password = True

    # Anyone already signed in as this person — including whoever caused the
    # reset to be needed — is signed out.
    await db.execute(
        text("UPDATE refresh_tokens SET is_revoked = TRUE WHERE user_id = :u AND is_revoked = FALSE"),
        {"u": person.id},
    )
    revoked_assertions = await mfa.revoke_all_for_user(db, user_id=person.id)

    await audit.record(
        db, action="user.password_reset", target_type="user", target_id=person.id,
        details={
            "name": person.name,
            "generated": generated,
            "step_up_assertions_revoked": revoked_assertions,
        },
        **ctx.audit_kwargs(),
    )

    await notification_service.notify_single_user(
        db,
        tenant_id=person.tenant_id,
        actor_id=ctx.user.id,
        recipient_id=person.id,
        event_type="password_reset_by_admin",
        title="Your password was reset",
        message=(
            f"{ctx.user.name} gave you a temporary password. You were asked to "
            "choose a new one when you signed in with it."
        ),
        entity_type="user",
        entity_id=person.id,
        entity_name=person.name,
    )

    await db.commit()
    return {
        "message": f"{person.name} has a temporary password and will be asked to "
                   "choose their own at next sign-in.",
        "user": {"id": person.id, "name": person.name, "email": person.email,
                 "employee_code": person.employee_code},
        # Shown once. The UI says so.
        "temporary_password": temporary,
    }


# ─── HR access ───────────────────────────────────────────────────────────────
#
# Making someone HR adds payroll and expense-claim powers for the whole
# organisation on top of their own role (users.is_hr; see migration
# g2b3c4d5e6f7). Their own role is untouched, so an employee made HR keeps
# their attendance, leave and My Pay screens and signs in to the HR portal
# with the same account.

class HrIn(BaseModel):
    is_hr: bool


@router.get("/accounts/hr")
async def list_hr(
    ctx: SecurityContext = Depends(require_permission("role.assign")),
    db: AsyncSession = Depends(get_db),
):
    """Everyone in the organisation who currently has HR access."""
    org = require_organisation(ctx)
    rows = (await db.execute(
        select(User).where(User.tenant_id == org, User.is_hr.is_(True)).order_by(User.name)
    )).scalars().all()
    return [{"id": u.id, "name": u.name, "email": u.email, "employee_code": u.employee_code,
             "role": u.role, "is_active": u.is_active} for u in rows]


@router.put("/accounts/{user_id}/hr")
async def set_hr(
    user_id: int,
    data: HrIn,
    ctx: SecurityContext = Depends(require_permission("role.assign")),
    db: AsyncSession = Depends(get_db),
):
    org = require_organisation(ctx)
    if user_id == ctx.user.id:
        raise HTTPException(400, "You cannot change your own HR access.")
    person = (await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == org)
    )).scalars().first()
    if not person:
        raise HTTPException(404, "Person not found in this organisation.")
    if person.role not in ("employee", "org_admin"):
        raise HTTPException(
            409, "HR access is for employees and Org Admins. A Tenant Admin already has every payroll power.",
        )
    if not person.is_active and data.is_hr:
        raise HTTPException(409, "This account is deactivated.")

    if bool(person.is_hr) == data.is_hr:
        return {"id": person.id, "name": person.name, "is_hr": person.is_hr,
                "message": f"No change: {person.name} {'already has' if data.is_hr else 'does not have'} HR access."}

    person.is_hr = data.is_hr
    if data.is_hr:
        await audit.record(db, action="user.hr_granted", target_type="user", target_id=person.id,
                           details={"name": person.name, "role": person.role}, **ctx.audit_kwargs())
    else:
        await audit.record(db, action="user.hr_revoked", target_type="user", target_id=person.id,
                           details={"name": person.name, "role": person.role}, **ctx.audit_kwargs())
    await notification_service.notify_single_user(
        db,
        tenant_id=person.tenant_id,
        actor_id=ctx.user.id,
        recipient_id=person.id,
        event_type="hr_access_changed",
        title="You now have HR access" if data.is_hr else "Your HR access was removed",
        message=(
            f"{ctx.user.name} gave you HR access. Sign in through the HR portal to run payroll."
            if data.is_hr else f"{ctx.user.name} removed your HR access."
        ),
        entity_type="user",
        entity_id=person.id,
        entity_name=person.name,
    )
    await db.commit()
    return {"id": person.id, "name": person.name, "is_hr": person.is_hr,
            "message": f"{person.name} {'now has' if data.is_hr else 'no longer has'} HR access."}
