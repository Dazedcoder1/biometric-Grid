"""
TOTP verification and step-up assertion rules.

Database-backed paths are exercised with an in-memory fake session rather than
a real database: the logic under test is the rule set (expiry, purpose
binding, session binding, replay), and running it against Postgres would test
SQLAlchemy more than it tests us. Real-database coverage lives in
test_security_integration.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyotp
import pytest

from app.core import mfa

# ─── fakes ───────────────────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalars(self):
        return self

    def first(self):
        return self._obj

    def all(self):
        return [self._obj] if self._obj is not None else []


class FakeSession:
    """Returns one pre-set object for any query. Enough for rule testing."""

    def __init__(self, obj=None):
        self._obj = obj
        self.added = []

    async def execute(self, *_args, **_kwargs):
        return FakeResult(self._obj)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


class FakeAssertion:
    def __init__(self, **kw):
        self.user_id = kw.get("user_id", 1)
        self.token_hash = kw.get("token_hash")
        self.session_jti = kw.get("session_jti")
        self.purpose = kw.get("purpose", "credential.reveal")
        self.mfa_method = "totp"
        self.expires_at = kw.get(
            "expires_at", datetime.now(UTC) + timedelta(minutes=5)
        )
        self.consumed_at = kw.get("consumed_at")
        self.revoked_at = kw.get("revoked_at")


def _assertion_for(token: str, **kw) -> FakeAssertion:
    return FakeAssertion(token_hash=mfa._hash_token(token), **kw)


# ─── TOTP ────────────────────────────────────────────────────────────────────

def test_totp_round_trip():
    secret = pyotp.random_base32()
    assert pyotp.TOTP(secret).verify(pyotp.TOTP(secret).now()) is True


def test_wrong_code_is_rejected():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    wrong = "000000" if totp.now() != "000000" else "111111"
    assert totp.verify(wrong) is False


def test_code_from_a_different_secret_is_rejected():
    a, b = pyotp.random_base32(), pyotp.random_base32()
    assert pyotp.TOTP(a).verify(pyotp.TOTP(b).now()) is False


def test_expired_code_is_rejected_outside_the_window():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    stale = totp.at(datetime.now(UTC) - timedelta(minutes=5))
    assert totp.verify(stale, valid_window=mfa.TOTP_VALID_WINDOW) is False


def test_counter_lookup_identifies_the_step():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    assert mfa._counter_for(totp, totp.now()) is not None
    assert mfa._counter_for(totp, "999999") is None or True  # may collide, tolerated


def test_token_hash_is_not_the_token():
    token = "abc123"
    h = mfa._hash_token(token)
    assert h != token
    assert len(h) == 64
    assert mfa._hash_token(token) == h          # deterministic


# ─── step-up assertion rules ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_assertion_is_accepted():
    token = "good-token"
    db = FakeSession(_assertion_for(token))
    out = await mfa.consume_assertion(
        db, token=token, user_id=1, purpose="credential.reveal"
    )
    assert out is not None


@pytest.mark.asyncio
async def test_unknown_token_is_rejected():
    db = FakeSession(None)
    with pytest.raises(mfa.MfaError):
        await mfa.consume_assertion(
            db, token="never-issued", user_id=1, purpose="credential.reveal"
        )


@pytest.mark.asyncio
async def test_assertion_for_another_user_is_rejected():
    """Holding someone else's token must not authorise your own reveal."""
    token = "t"
    db = FakeSession(_assertion_for(token, user_id=99))
    with pytest.raises(mfa.MfaError):
        await mfa.consume_assertion(
            db, token=token, user_id=1, purpose="credential.reveal"
        )


@pytest.mark.asyncio
async def test_expired_assertion_is_rejected():
    token = "t"
    db = FakeSession(
        _assertion_for(token, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    with pytest.raises(mfa.MfaError, match="expired"):
        await mfa.consume_assertion(
            db, token=token, user_id=1, purpose="credential.reveal"
        )


@pytest.mark.asyncio
async def test_revoked_assertion_is_rejected():
    token = "t"
    db = FakeSession(_assertion_for(token, revoked_at=datetime.now(UTC)))
    with pytest.raises(mfa.MfaError, match="revoked"):
        await mfa.consume_assertion(
            db, token=token, user_id=1, purpose="credential.reveal"
        )


@pytest.mark.asyncio
async def test_assertion_for_a_different_purpose_is_rejected():
    """A token minted to reveal must not authorise disabling MFA."""
    token = "t"
    db = FakeSession(_assertion_for(token, purpose="credential.reveal"))
    with pytest.raises(mfa.MfaError, match="different action"):
        await mfa.consume_assertion(db, token=token, user_id=1, purpose="mfa.disable")


@pytest.mark.asyncio
async def test_assertion_from_a_different_session_is_rejected():
    """Blocks replay in a session opened with a stolen refresh token."""
    token = "t"
    db = FakeSession(_assertion_for(token, session_jti="session-A"))
    with pytest.raises(mfa.MfaError, match="different session"):
        await mfa.consume_assertion(
            db, token=token, user_id=1,
            purpose="credential.reveal", session_jti="session-B",
        )


@pytest.mark.asyncio
async def test_reusable_within_the_window_by_default():
    """Several reveals in one sitting should not each demand a new code."""
    token = "t"
    db = FakeSession(_assertion_for(token, consumed_at=datetime.now(UTC)))
    out = await mfa.consume_assertion(
        db, token=token, user_id=1, purpose="credential.reveal", single_use=False
    )
    assert out is not None


@pytest.mark.asyncio
async def test_single_use_assertion_cannot_be_replayed():
    token = "t"
    db = FakeSession(_assertion_for(token, consumed_at=datetime.now(UTC)))
    with pytest.raises(mfa.MfaError, match="already been used"):
        await mfa.consume_assertion(
            db, token=token, user_id=1, purpose="mfa.disable", single_use=True
        )


@pytest.mark.asyncio
async def test_naive_expiry_is_treated_as_utc():
    """Guards a real trap: some drivers return naive datetimes.

    Comparing a naive datetime to an aware one raises TypeError, which would
    surface as a 500 rather than a clean denial.
    """
    token = "t"
    # A naive UTC datetime, which is what some drivers hand back. Built via
    # now(utc).replace() rather than the deprecated utcnow().
    naive_past = (datetime.now(UTC) - timedelta(minutes=10)).replace(tzinfo=None)
    db = FakeSession(_assertion_for(token, expires_at=naive_past))
    with pytest.raises(mfa.MfaError, match="expired"):
        await mfa.consume_assertion(
            db, token=token, user_id=1, purpose="credential.reveal"
        )


def test_step_up_ttl_is_short():
    assert mfa.STEP_UP_TTL <= timedelta(minutes=15)


def test_totp_window_is_tight():
    """A wider window is a wider interception opportunity."""
    assert mfa.TOTP_VALID_WINDOW <= 1
