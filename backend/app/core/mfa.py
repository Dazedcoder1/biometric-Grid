"""
TOTP enrolment and step-up assertions.

Step-up rather than login MFA: prompting at every login taxes everyone for a
capability most people use rarely, while prompting at reveal puts the friction
exactly where the risk is. ARCHITECTURE.md §6.

Library: **pyotp**. RFC 6238 is small enough to implement badly and there is no
reason to — pyotp is the de facto Python implementation, widely used, and its
`verify(valid_window=...)` handles clock drift correctly. No custom
cryptography, per the project ground rules.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.models.security import MfaCredential, StepUpAssertion

#: How long a step-up assertion stays valid. Short enough that a walked-away
#: laptop is not an open vault; long enough to reveal several credentials in
#: one sitting without re-prompting each time.
STEP_UP_TTL = timedelta(minutes=5)

#: Accept codes one 30-second step either side of now, for clock drift.
#: Larger windows meaningfully widen the interception window.
TOTP_VALID_WINDOW = 1

ISSUER = "GridSphere"


class MfaError(RuntimeError):
    """MFA operation failed. The message is safe to show a user."""


# ─────────────────────────────────────────────────────────────────────────────
# Enrolment
# ─────────────────────────────────────────────────────────────────────────────

async def begin_enrolment(
    db: AsyncSession, *, user_id: int, account_label: str
) -> tuple[MfaCredential, str, str]:
    """
    Create an *unconfirmed* TOTP credential.

    Returns (credential, secret, provisioning_uri). The secret is returned once,
    here, so it can be rendered as a QR code. It is never retrievable again.

    Unconfirmed on purpose: a credential that satisfied step-up checks the
    instant it was created would let anyone who reached this endpoint enrol a
    factor they control and walk straight past the gate. Possession has to be
    proven first.
    """
    secret = pyotp.random_base32()

    cred = MfaCredential(
        user_id=user_id,
        kind="totp",
        secret_encrypted=crypto.encrypt(secret),
        label=account_label,
        confirmed_at=None,
    )
    db.add(cred)
    await db.flush()

    uri = pyotp.TOTP(secret).provisioning_uri(name=account_label, issuer_name=ISSUER)
    return cred, secret, uri


async def confirm_enrolment(db: AsyncSession, *, user_id: int, code: str) -> MfaCredential:
    """Prove possession and activate the most recent unconfirmed credential."""
    cred = (
        await db.execute(
            select(MfaCredential)
            .where(
                MfaCredential.user_id == user_id,
                MfaCredential.kind == "totp",
                MfaCredential.confirmed_at.is_(None),
            )
            .order_by(MfaCredential.id.desc())
            .limit(1)
        )
    ).scalars().first()

    if not cred:
        raise MfaError("No pending enrolment. Start again.")

    secret = crypto.decrypt(cred.secret_encrypted)
    if not secret:
        # Only happens if GITHUB_ENC_KEY changed since enrolment began.
        raise MfaError("Stored secret is unreadable. Start enrolment again.")

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=TOTP_VALID_WINDOW):
        raise MfaError("That code is not correct.")

    cred.confirmed_at = datetime.now(UTC)
    cred.last_used_counter = _counter_for(totp, code)
    await db.flush()
    return cred


async def has_confirmed_factor(db: AsyncSession, *, user_id: int) -> bool:
    row = (
        await db.execute(
            select(MfaCredential.id).where(
                MfaCredential.user_id == user_id,
                MfaCredential.confirmed_at.is_not(None),
            ).limit(1)
        )
    ).first()
    return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# Verification and step-up
# ─────────────────────────────────────────────────────────────────────────────

def _counter_for(totp: pyotp.TOTP, code: str) -> int | None:
    """
    Which time step produced this code, so it can be refused a second time.

    A TOTP code is valid for its whole window. Without remembering the last
    accepted step, an intercepted code — over someone's shoulder, from a
    phishing page — works again until the window closes.
    """
    now = datetime.now(UTC)
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        at = now + timedelta(seconds=offset * totp.interval)
        if totp.at(at) == code:
            return int(at.timestamp()) // totp.interval
    return None


async def verify_and_issue(
    db: AsyncSession,
    *,
    user_id: int,
    code: str,
    purpose: str,
    session_jti: str | None = None,
) -> tuple[str, datetime]:
    """
    Check a TOTP code and mint a step-up assertion.

    Returns (token, expires_at). Only the token's SHA-256 is stored, so the
    plaintext exists solely in this response — a leaked database row cannot be
    replayed.

    Does not commit; the caller owns the transaction, so the assertion and its
    audit entry land together.
    """
    cred = (
        await db.execute(
            select(MfaCredential)
            .where(
                MfaCredential.user_id == user_id,
                MfaCredential.kind == "totp",
                MfaCredential.confirmed_at.is_not(None),
            )
            .order_by(MfaCredential.id.desc())
            .limit(1)
        )
    ).scalars().first()

    if not cred:
        raise MfaError("No second factor is enrolled for this account.")

    secret = crypto.decrypt(cred.secret_encrypted)
    if not secret:
        raise MfaError("Stored secret is unreadable. Re-enrol your authenticator.")

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=TOTP_VALID_WINDOW):
        raise MfaError("That code is not correct.")

    counter = _counter_for(totp, code)
    if counter is not None and cred.last_used_counter is not None:
        if counter <= cred.last_used_counter:
            raise MfaError("That code has already been used. Wait for the next one.")
    cred.last_used_counter = counter

    # 256 bits: this token authorises decryption, so it is sized like a key
    # rather than like a session id.
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + STEP_UP_TTL

    db.add(
        StepUpAssertion(
            user_id=user_id,
            token_hash=_hash_token(token),
            session_jti=session_jti,
            purpose=purpose,
            mfa_method="totp",
            expires_at=expires_at,
        )
    )
    await db.flush()
    return token, expires_at


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def consume_assertion(
    db: AsyncSession,
    *,
    token: str,
    user_id: int,
    purpose: str,
    session_jti: str | None = None,
    single_use: bool = False,
) -> StepUpAssertion:
    """
    Validate a step-up token. Raises MfaError with a specific reason if not.

    Every condition is checked explicitly rather than with one broad query, so
    a denial can say which rule failed — both for the user and for the audit
    entry. Vague failures make abuse harder to spot.

    single_use=False by default: within the five-minute window a user may
    reveal several credentials without re-entering a code. Pass True for
    genuinely one-shot operations such as disabling MFA.
    """
    row = (
        await db.execute(
            select(StepUpAssertion).where(
                StepUpAssertion.token_hash == _hash_token(token)
            )
        )
    ).scalars().first()

    if row is None:
        raise MfaError("Re-authentication required.")

    now = datetime.now(UTC)

    # Guard against a token minted for a different account.
    if row.user_id != user_id:
        raise MfaError("Re-authentication required.")

    if row.revoked_at is not None:
        raise MfaError("This re-authentication was revoked.")

    if row.consumed_at is not None and single_use:
        raise MfaError("This re-authentication has already been used.")

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise MfaError("Re-authentication expired. Confirm your code again.")

    if row.purpose != purpose:
        # Minted for one action, presented for another.
        raise MfaError("Re-authentication was for a different action.")

    if row.session_jti and session_jti and row.session_jti != session_jti:
        # Obtained in another session — including one an attacker opened with a
        # stolen refresh token.
        raise MfaError("Re-authentication belongs to a different session.")

    if single_use:
        row.consumed_at = now
        await db.flush()

    return row


async def revoke_all_for_user(db: AsyncSession, *, user_id: int) -> int:
    """Kill every live assertion — on password change, or suspected abuse."""
    rows = (
        await db.execute(
            select(StepUpAssertion).where(
                StepUpAssertion.user_id == user_id,
                StepUpAssertion.revoked_at.is_(None),
            )
        )
    ).scalars().all()

    now = datetime.now(UTC)
    for row in rows:
        row.revoked_at = now
    await db.flush()
    return len(rows)
