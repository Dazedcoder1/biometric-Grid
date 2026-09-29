"""
MFA enrolment and step-up verification.

Enrolment is two-step — create a secret, then prove possession — because a
credential that satisfied step-up the instant it was created would let anyone
reaching this endpoint enrol a factor they control and walk past the gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_security import SecurityContext, get_security_context
from app.core import audit, mfa
from app.db.session import get_db

router = APIRouter()


class EnrolStart(BaseModel):
    label: str | None = Field(None, max_length=128)


class CodeIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)


class StepUpIn(CodeIn):
    purpose: str = Field("credential.reveal", max_length=96)


@router.get("/mfa/status")
async def mfa_status(
    ctx: SecurityContext = Depends(get_security_context),
    db: AsyncSession = Depends(get_db),
):
    enrolled = await mfa.has_confirmed_factor(db, user_id=ctx.user.id)
    return {"enrolled": enrolled, "method": "totp" if enrolled else None}


@router.post("/mfa/enrol")
async def begin_enrolment(
    data: EnrolStart,
    ctx: SecurityContext = Depends(get_security_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Start enrolment. Returns the secret and a provisioning URI for a QR code.

    This is the only time the secret leaves the server. It is stored encrypted
    and never returned again — losing it means re-enrolling.
    """
    if await mfa.has_confirmed_factor(db, user_id=ctx.user.id):
        raise HTTPException(
            409,
            "An authenticator is already enrolled. Remove it before enrolling "
            "another.",
        )

    label = data.label or ctx.user.email or f"user-{ctx.user.id}"
    _, secret, uri = await mfa.begin_enrolment(
        db, user_id=ctx.user.id, account_label=label
    )

    await audit.record(
        db,
        action="mfa.enrolment_started",
        target_type="user",
        target_id=ctx.user.id,
        **ctx.audit_kwargs(),
    )
    await db.commit()

    return {
        "secret": secret,
        "provisioning_uri": uri,
        "next": "Scan this, then POST the 6-digit code to /api/vault/mfa/enrol/confirm",
    }


@router.post("/mfa/enrol/confirm")
async def confirm_enrolment(
    data: CodeIn,
    ctx: SecurityContext = Depends(get_security_context),
    db: AsyncSession = Depends(get_db),
):
    try:
        await mfa.confirm_enrolment(db, user_id=ctx.user.id, code=data.code)
    except mfa.MfaError as exc:
        await audit.record(
            db,
            action="mfa.enrolment_failed",
            result="denied",
            reason=str(exc),
            target_type="user",
            target_id=ctx.user.id,
            **ctx.audit_kwargs(),
        )
        await db.commit()
        raise HTTPException(400, str(exc)) from exc

    await audit.record(
        db,
        action="mfa.enrolled",
        target_type="user",
        target_id=ctx.user.id,
        **ctx.audit_kwargs(),
    )
    await db.commit()
    return {"enrolled": True}


@router.post("/mfa/step-up")
async def step_up(
    data: StepUpIn,
    ctx: SecurityContext = Depends(get_security_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a TOTP code for a short-lived step-up token.

    Send it back as the `X-Step-Up-Token` header on the guarded request. Header
    rather than body: it applies to the request, not the payload, and keeps it
    out of any JSON logging.
    """
    try:
        token, expires_at = await mfa.verify_and_issue(
            db,
            user_id=ctx.user.id,
            code=data.code,
            purpose=data.purpose,
            session_jti=ctx.session_jti,
        )
    except mfa.MfaError as exc:
        await audit.record(
            db,
            action="mfa.failed",
            result="denied",
            reason=str(exc),
            target_type="user",
            target_id=ctx.user.id,
            details={"purpose": data.purpose},
            **ctx.audit_kwargs(),
        )
        await db.commit()
        raise HTTPException(401, str(exc)) from exc

    await audit.record(
        db,
        action="mfa.verified",
        target_type="user",
        target_id=ctx.user.id,
        mfa_method="totp",
        details={"purpose": data.purpose},
        **ctx.audit_kwargs(),
    )
    await db.commit()

    return {
        "step_up_token": token,
        "expires_at": expires_at,
        "header": "X-Step-Up-Token",
    }
