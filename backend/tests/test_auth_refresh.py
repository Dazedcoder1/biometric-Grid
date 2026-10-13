"""
Renewing a session with a refresh token.

The endpoint used to compare the timezone-aware expires_at column with a
naive datetime.utcnow(), which raises — every refresh returned 500, so
sessions died when the access token expired and every screen showed
"Invalid or expired token". These pin the fixed behaviour.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException

from app.api.routes import auth as auth_routes
from app.core.security import create_refresh_token, decode_token

UTC = dt.timezone.utc


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Res:
    def __init__(self, v):
        self.v = v

    def scalars(self):
        return self

    def first(self):
        return self.v


class FakeDB:
    """execute() answers the refresh-token lookup, then the user lookup."""

    def __init__(self, record, user):
        self.results = [record, user]
        self.added, self.commits = [], 0

    async def execute(self, _stmt):
        return _Res(self.results.pop(0) if self.results else None)

    def add(self, o):
        self.added.append(o)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _user(**kw):
    base = dict(id=7, role="employee", tenant_id=1, dept_id=2, is_active=True,
                must_change_password=False, is_hr=False)
    return Obj(**{**base, **kw})


def _refresh_for(user):
    token, jti = create_refresh_token({"user_id": user.id, "role": "employee", "tenant_id": 1, "dept_id": 2})
    return token, jti


def _record(jti, *, expires_at, revoked=False):
    return Obj(token_jti=jti, user_id=7, expires_at=expires_at, is_revoked=revoked)


async def test_refresh_works_with_a_timezone_aware_expiry():
    user = _user()
    token, jti = _refresh_for(user)
    rec = _record(jti, expires_at=dt.datetime.now(UTC) + dt.timedelta(days=3))
    db = FakeDB(rec, user)
    out = await auth_routes.refresh_token(auth_routes.RefreshRequest(refresh_token=token), db)
    assert out["access_token"] and out["refresh_token"] and out["refresh_token"] != token
    assert rec.is_revoked is True                       # single use
    assert db.added and db.commits == 1                 # the new refresh token is stored
    new_record = db.added[0]
    assert new_record.expires_at.tzinfo is not None     # stored aware


async def test_rows_written_before_the_fix_still_work():
    user = _user()
    token, jti = _refresh_for(user)
    naive = dt.datetime.utcnow() + dt.timedelta(days=1)
    out = await auth_routes.refresh_token(
        auth_routes.RefreshRequest(refresh_token=token), FakeDB(_record(jti, expires_at=naive), user))
    assert out["access_token"]


async def test_new_tokens_come_from_the_user_as_they_are_now():
    user = _user(role="org_admin", dept_id=9, is_hr=True)   # changed since the old token
    token, jti = _refresh_for(user)
    out = await auth_routes.refresh_token(
        auth_routes.RefreshRequest(refresh_token=token),
        FakeDB(_record(jti, expires_at=dt.datetime.now(UTC) + dt.timedelta(days=1)), user))
    claims = decode_token(out["access_token"])
    assert (claims["role"], claims["dept_id"], claims["is_hr"]) == ("org_admin", 9, True)


@pytest.mark.parametrize("case", ["expired", "revoked", "missing", "inactive", "garbage", "access_token"])
async def test_refused_cleanly_with_401(case):
    user = _user(is_active=(case != "inactive"))
    token, jti = _refresh_for(user)
    when = dt.datetime.now(UTC) + (dt.timedelta(days=-1) if case == "expired" else dt.timedelta(days=1))
    rec = None if case == "missing" else _record(jti, expires_at=when, revoked=(case == "revoked"))
    if case == "garbage":
        token = "not-a-token"
    if case == "access_token":
        from app.core.security import create_access_token
        token = create_access_token({"user_id": 7, "role": "employee"})
    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_token(auth_routes.RefreshRequest(refresh_token=token), FakeDB(rec, user))
    assert exc.value.status_code == 401
    if case == "inactive":
        assert rec.is_revoked is True                   # and it cannot be tried again
