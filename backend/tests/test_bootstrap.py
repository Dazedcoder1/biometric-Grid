"""
The Super Admin created from .env at startup, and the demo Super Admin
switched off — plus the typed-name check on deleting a whole organisation.

The bootstrap's promise is narrow and these pin it: create when missing,
NEVER overwrite (a password changed after first sign-in must survive a
restart), refuse a weak password, refuse to promote someone else's account,
and switch off super@demo.local — whose password is in this repository —
once a real Super Admin is configured.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.super_admin import tenants as tenants_mod
from app.core import bootstrap
from app.core.security import verify_password


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Res:
    def __init__(self, v):
        self._v = v

    def scalars(self):
        return self

    def first(self):
        return self._v


class FakeDB:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.commits = 0

    async def execute(self, _stmt):
        return _Res(self.existing)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def configured(monkeypatch):
    def use(email="Boss@Example.com", password="Correct-Horse-42-battery", name="Boss"):
        monkeypatch.setattr(bootstrap.settings, "SUPER_ADMIN_EMAIL", email)
        monkeypatch.setattr(bootstrap.settings, "SUPER_ADMIN_PASSWORD", password)
        monkeypatch.setattr(bootstrap.settings, "SUPER_ADMIN_NAME", name)
    return use


async def test_creates_when_missing_and_forces_a_new_password(configured):
    configured()
    db = FakeDB(existing=None)
    assert await bootstrap.ensure_super_admin(db) == "created"
    u = db.added[0]
    assert u.role == "super_admin" and u.tenant_id is None
    assert u.email == "boss@example.com"                     # normalised
    assert verify_password("Correct-Horse-42-battery", u.password_hash)
    assert u.must_change_password is True                    # .env is a way in, not a keeper
    assert db.commits == 1


async def test_never_overwrites_an_existing_super_admin(configured):
    configured()
    existing = Obj(role="super_admin", password_hash="kept", email="boss@example.com")
    db = FakeDB(existing=existing)
    assert await bootstrap.ensure_super_admin(db) == "exists"
    assert existing.password_hash == "kept"
    assert db.added == [] and db.commits == 0


async def test_refuses_to_promote_someone_elses_account(configured):
    configured()
    db = FakeDB(existing=Obj(role="employee", email="boss@example.com"))
    assert await bootstrap.ensure_super_admin(db) == "email taken"
    assert db.added == [] and db.commits == 0


@pytest.mark.parametrize("weak", ["short1", "no-digits-at-all-here", "123456789012345"])
async def test_refuses_a_weak_password(configured, weak):
    configured(password=weak)
    db = FakeDB()
    assert await bootstrap.ensure_super_admin(db) == "weak password"
    assert db.added == []


async def test_does_nothing_when_not_configured(configured):
    configured(email="", password="")
    assert await bootstrap.ensure_super_admin(FakeDB()) == "not configured"


async def test_demo_super_admin_is_switched_off_once_a_real_one_is_configured(configured):
    configured()
    demo = Obj(email="super@demo.local", is_active=True)
    db = FakeDB(existing=demo)
    assert await bootstrap.disable_demo_super_admin(db) is True
    assert demo.is_active is False and db.commits == 1


async def test_demo_super_admin_left_alone_without_a_real_one(configured):
    configured(email="", password="")
    demo = Obj(email="super@demo.local", is_active=True)
    assert await bootstrap.disable_demo_super_admin(FakeDB(existing=demo)) is False
    assert demo.is_active is True


async def test_bootstrap_never_stops_startup(monkeypatch):
    class Boom:
        async def __aenter__(self):
            raise RuntimeError("database down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bootstrap, "AsyncSessionLocal", lambda: Boom())
    await bootstrap.run()   # logs, does not raise


# ─── deleting a whole organisation ──────────────────────────────────────────

async def test_purge_needs_the_exact_name(monkeypatch):
    async def get(db, tid):
        return Obj(id=tid, name="TEstORG")

    monkeypatch.setattr(tenants_mod, "_get_tenant_or_404", get)
    with pytest.raises(HTTPException) as exc:
        await tenants_mod.purge_tenant(
            9, tenants_mod.PurgeIn(confirm_name="testorg"), Obj(), Obj(id=1, role="super_admin"), FakeDB())
    assert exc.value.status_code == 400
    assert "TEstORG" in exc.value.detail


async def test_purge_audits_first_then_deletes(monkeypatch):
    order = []

    async def get(db, tid):
        return Obj(id=tid, name="Old Co")

    async def inventory(db, tid):
        return [{"table": "users", "label": "people", "count": 7}]

    async def record(db, **kw):
        order.append(("audit", kw["action"], kw["details"]))

    async def purge(db, ids):
        order.append(("purge", ids, None))
        return 1

    monkeypatch.setattr(tenants_mod, "_get_tenant_or_404", get)
    monkeypatch.setattr(tenants_mod, "_inventory", inventory)
    monkeypatch.setattr(tenants_mod.audit, "record", record)
    import app.services.tenant_purge as tp
    monkeypatch.setattr(tp, "purge_tenants", purge)

    req = Obj(client=Obj(host="1.2.3.4"), headers={"user-agent": "t"})
    db = FakeDB()
    out = await tenants_mod.purge_tenant(
        9, tenants_mod.PurgeIn(confirm_name=" Old Co "), req, Obj(id=1, role="super_admin"), db)

    assert [o[0] for o in order] == ["audit", "purge"]
    assert order[0][1] == "organisation.purged"
    assert order[0][2]["held"] == {"users": 7}
    assert order[1][1] == [9]
    assert db.commits == 1
    assert "Old Co" in out["message"]
