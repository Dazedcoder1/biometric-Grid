"""
Access isolation: who can reach which credential.

`effective_level` is the single place that answers that question, so it is
tested directly. A second implementation in a route handler is how
authorisation bugs are born, and these tests exist to make sure this stays the
only one.

Share lookups need a database, so those paths are covered by the integration
tests. What runs here is the decision logic — tenant isolation, ownership, and
the level ordering — which is where a mistake would be silent.
"""

from __future__ import annotations

import pytest

from app.services import vault_service as svc


class FakeUser:
    def __init__(self, user_id: int, tenant_id: int):
        self.id = user_id
        self.tenant_id = tenant_id


class FakeCredential:
    def __init__(self, cred_id: int, tenant_id: int, owner_id: int):
        self.id = cred_id
        self.tenant_id = tenant_id
        self.owner_id = owner_id


class NoShares:
    """A session whose share lookup always comes back empty."""

    async def execute(self, *_a, **_kw):
        class R:
            def scalars(self_inner):
                return self_inner

            def all(self_inner):
                return []

        return R()


# ─── level ordering ──────────────────────────────────────────────────────────

def test_levels_are_ordered_weakest_to_strongest():
    assert svc.LEVELS == ("view", "reveal", "edit", "reshare", "manage")


def test_stronger_level_implies_weaker():
    assert svc.allows("manage", "view") is True
    assert svc.allows("manage", "reveal") is True
    assert svc.allows("edit", "reveal") is True
    assert svc.allows("reveal", "view") is True


def test_weaker_level_does_not_imply_stronger():
    assert svc.allows("view", "reveal") is False
    assert svc.allows("reveal", "edit") is False
    assert svc.allows("edit", "manage") is False


def test_view_alone_never_reveals():
    """The distinction the whole product rests on."""
    assert svc.allows("view", "reveal") is False


def test_no_level_allows_nothing():
    for required in svc.LEVELS:
        assert svc.allows(None, required) is False


def test_unknown_level_allows_nothing():
    """Deny-by-default: a typo or a corrupted row must not grant access."""
    assert svc.allows("superuser", "view") is False
    assert svc.allows("", "view") is False
    assert svc.allows("VIEW", "view") is False        # case matters


def test_unknown_requirement_is_denied():
    assert svc.allows("manage", "credential.destroy_everything") is False


# ─── ownership and tenancy ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_owner_gets_manage():
    user = FakeUser(1, tenant_id=10)
    cred = FakeCredential(100, tenant_id=10, owner_id=1)
    assert await svc.effective_level(NoShares(), user=user, credential=cred) == "manage"


@pytest.mark.asyncio
async def test_stranger_in_same_tenant_gets_nothing():
    """No share, not the owner — nothing, even inside the same organisation."""
    user = FakeUser(2, tenant_id=10)
    cred = FakeCredential(100, tenant_id=10, owner_id=1)
    assert await svc.effective_level(NoShares(), user=user, credential=cred) is None


@pytest.mark.asyncio
async def test_other_tenant_is_refused_even_for_the_owner_id():
    """
    Tenant isolation is checked FIRST, before ownership or shares.

    The case that matters: a credential row whose owner_id happens to match a
    user in a different tenant — through a bug, a bad import, or a manipulated
    request. Ownership must not rescue it.
    """
    user = FakeUser(1, tenant_id=10)
    cred = FakeCredential(100, tenant_id=99, owner_id=1)
    assert await svc.effective_level(NoShares(), user=user, credential=cred) is None


@pytest.mark.asyncio
async def test_other_tenant_is_refused_with_shares_present():
    user = FakeUser(2, tenant_id=10)
    cred = FakeCredential(100, tenant_id=99, owner_id=5)
    assert await svc.effective_level(NoShares(), user=user, credential=cred) is None


# ─── super admin ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_gets_manage_anywhere():
    """Unrestricted by requirement. Every such access is audited separately."""
    user = FakeUser(1, tenant_id=10)
    cred = FakeCredential(100, tenant_id=99, owner_id=5)
    level = await svc.effective_level(
        NoShares(), user=user, credential=cred, grants_all=True
    )
    assert level == "manage"


@pytest.mark.asyncio
async def test_grants_all_bypasses_tenant_isolation_deliberately():
    """
    Documenting behaviour rather than endorsing it.

    Super Admin crossing tenant boundaries is the stated requirement. It is
    also why SECURITY.md lists a compromised Super Admin as undefendable by
    cryptography, and why the audit log distinguishes their access.
    """
    user = FakeUser(1, tenant_id=1)
    for tenant in (2, 3, 999):
        cred = FakeCredential(1, tenant_id=tenant, owner_id=42)
        assert await svc.effective_level(
            NoShares(), user=user, credential=cred, grants_all=True
        ) == "manage"


# ─── require_level ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_require_level_raises_404_not_403():
    """
    No access reports "not found", not "forbidden".

    Distinguishing the two lets somebody walk credential ids and learn what a
    tenant holds without ever reading one.
    """
    from fastapi import HTTPException

    user = FakeUser(2, tenant_id=10)
    cred = FakeCredential(100, tenant_id=10, owner_id=1)

    with pytest.raises(HTTPException) as exc:
        await svc.require_level(NoShares(), user=user, credential=cred, required="view")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_level_returns_the_level_when_allowed():
    user = FakeUser(1, tenant_id=10)
    cred = FakeCredential(100, tenant_id=10, owner_id=1)
    level = await svc.require_level(
        NoShares(), user=user, credential=cred, required="reveal"
    )
    assert level == "manage"
