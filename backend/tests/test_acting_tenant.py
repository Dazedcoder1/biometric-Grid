"""
X-Acting-Tenant-Id must not become a way to reach another organisation.

The header lets a Super Admin say which organisation they are administering,
because their account has no tenant of its own. That is a genuine need and a
genuinely dangerous shape: a client-supplied value that selects whose data a
request operates on. The whole of its safety rests on one check — that the
caller's role is super_admin — so that check is what these tests pin down.

The dependency is exercised directly rather than through HTTP. Every route
under /api/tenant resolves its tenant through this one function, so proving it
here proves it for all of them, and a route-level test would only confirm the
wiring of whichever route it happened to pick.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.dependencies import verify_tenant_api_key


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value


class FakeDB:
    """Answers each select with whatever the test queued, in order."""

    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _stmt):
        return FakeResult(self._results.pop(0) if self._results else None)


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


SUPER = Obj(id=1, role="super_admin", tenant_id=None, is_active=True)
TENANT_ADMIN = Obj(id=2, role="tenant_admin", tenant_id=7, is_active=True)
EMPLOYEE = Obj(id=3, role="employee", tenant_id=7, is_active=True)

ACME = Obj(id=7, name="Acme", api_key="k-acme")
OTHER = Obj(id=9, name="Other Co", api_key="k-other")

TOKEN = "Bearer header.payload.signature"


@pytest.fixture
def token_payload(monkeypatch):
    """Patch decode_token; these tests are about authorisation, not JWT parsing."""
    state = {"user_id": SUPER.id}

    def fake_decode(_token):
        return {"type": "access", "user_id": state["user_id"]}

    monkeypatch.setattr("app.api.dependencies.decode_token", fake_decode)
    return state


async def call(db, *, acting=None, authorization=TOKEN, api_key=None):
    return await verify_tenant_api_key(
        x_api_key=api_key,
        x_acting_tenant_id=acting,
        authorization=authorization,
        db=db,
    )


# ─── the super admin path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_super_admin_with_acting_header_gets_that_tenant(token_payload):
    token_payload["user_id"] = SUPER.id
    tenant = await call(FakeDB(SUPER, OTHER), acting=OTHER.id)
    assert tenant is OTHER


@pytest.mark.asyncio
async def test_super_admin_without_header_is_asked_to_choose(token_payload):
    token_payload["user_id"] = SUPER.id
    with pytest.raises(HTTPException) as exc:
        await call(FakeDB(SUPER))
    # 409, not 403: nothing is forbidden, the request is incomplete. The client
    # keys the organisation chooser off this status.
    assert exc.value.status_code == 409
    assert "choose an organisation" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_super_admin_naming_a_missing_tenant_gets_404(token_payload):
    token_payload["user_id"] = SUPER.id
    with pytest.raises(HTTPException) as exc:
        await call(FakeDB(SUPER, None), acting=4242)
    assert exc.value.status_code == 404


# ─── the escalation attempts ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_admin_cannot_act_on_another_tenant(token_payload):
    """The header is the whole attack surface. A tenant admin sending someone
    else's id must be refused."""
    token_payload["user_id"] = TENANT_ADMIN.id
    with pytest.raises(HTTPException) as exc:
        await call(FakeDB(TENANT_ADMIN), acting=OTHER.id)
    assert exc.value.status_code == 403
    assert "own organisation" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_tenant_admin_sending_their_own_id_is_allowed(token_payload):
    """Refusing this would break a client that sends the header unconditionally
    — which ours does, because it cannot know the role before the response."""
    token_payload["user_id"] = TENANT_ADMIN.id
    tenant = await call(FakeDB(TENANT_ADMIN, ACME), acting=TENANT_ADMIN.tenant_id)
    assert tenant is ACME


@pytest.mark.asyncio
async def test_tenant_admin_is_not_silently_redirected(token_payload):
    """
    The mismatch is refused rather than ignored. Falling back to their own
    tenant would let a client believe it was acting on another organisation
    while quietly writing to its own — a wrong answer is worse than an error.
    """
    token_payload["user_id"] = TENANT_ADMIN.id
    with pytest.raises(HTTPException):
        await call(FakeDB(TENANT_ADMIN, ACME), acting=OTHER.id)


@pytest.mark.asyncio
async def test_employee_is_refused_before_the_header_is_considered(token_payload):
    token_payload["user_id"] = EMPLOYEE.id
    with pytest.raises(HTTPException) as exc:
        await call(FakeDB(EMPLOYEE), acting=OTHER.id)
    assert exc.value.status_code == 403
    assert "Tenant Admins" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_api_key_path_ignores_the_acting_header(token_payload):
    """
    An API key names exactly one tenant. Letting a header override it would
    turn every device credential into a key for the whole platform.
    """
    tenant = await call(FakeDB(ACME), acting=OTHER.id, api_key="k-acme", authorization=None)
    assert tenant is ACME


@pytest.mark.asyncio
async def test_no_credentials_still_401(token_payload):
    with pytest.raises(HTTPException) as exc:
        await call(FakeDB(), acting=OTHER.id, authorization=None)
    assert exc.value.status_code == 401
