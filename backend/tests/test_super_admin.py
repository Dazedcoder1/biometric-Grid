"""
Platform administration: what a Super Admin can do to an organisation.

Pinned here because each of these was wrong before, silently:

* creation ignored the admin it was given, so new organisations had nobody who
  could sign in;
* the organisation list sent every tenant's API key to the browser;
* delete was one call away from erasing a company (and 500'd on any real one).

The route functions are called directly with a fake session rather than over
HTTP. What matters is the decision each makes — refuse, provision, redact —
not FastAPI's wiring, which every other route already exercises.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.super_admin import tenants as mod
from app.api.routes.super_admin.tenants import (
    OrganisationCreate,
    OrganisationRename,
    describe_blockers,
    key_hint,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────────────────────────────────────

class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeResult:
    def __init__(self, value=None):
        self._value = value

    def first(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value or []


class FakeSession:
    """Records what a route did. execute() answers from a queue, then None."""

    def __init__(self, *results):
        self.results = list(results)
        self.added = []
        self.deleted = []
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self._next_id = 100

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return FakeResult(self.results.pop(0) if self.results else None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            for attr in ("id", "department_id"):
                if hasattr(type(obj), attr) and getattr(obj, attr, None) is None:
                    self._next_id += 1
                    setattr(obj, attr, self._next_id)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        return None


class FakeRequest:
    client = Obj(host="10.0.0.1")
    headers = {"user-agent": "pytest"}


SUPER = Obj(id=1, role="super_admin", tenant_id=None, is_active=True)


@pytest.fixture
def audited(monkeypatch):
    """Capture audit writes instead of touching the hash chain."""
    calls = []

    async def fake_record(db, **kw):
        calls.append(kw)

    monkeypatch.setattr(mod.audit, "record", fake_record)
    return calls


def _valid(**over):
    base = dict(
        name="Acme Industries",
        admin_name="Priya Shah",
        admin_email="Priya@Acme.com",
        admin_password="Welcome2026",
    )
    base.update(over)
    return OrganisationCreate(**base)


# ─────────────────────────────────────────────────────────────────────────────
# Input validation
# ─────────────────────────────────────────────────────────────────────────────

def test_email_is_normalised_to_lower_case():
    # Sign-in compares emails exactly; two casings would be two accounts.
    assert _valid().admin_email == "priya@acme.com"


def test_names_are_trimmed_and_collapsed():
    org = _valid(name="  Acme    Industries ", admin_name=" Priya  Shah ")
    assert org.name == "Acme Industries"
    assert org.admin_name == "Priya Shah"


@pytest.mark.parametrize("pw", ["short1", "allletters", "12345678"])
def test_weak_passwords_are_refused(pw):
    with pytest.raises(ValidationError):
        _valid(admin_password=pw)


def test_blank_name_is_refused():
    with pytest.raises(ValidationError):
        _valid(name="   ")


def test_bad_email_is_refused():
    with pytest.raises(ValidationError):
        _valid(admin_email="not-an-email")


def test_rename_trims():
    assert OrganisationRename(name="  New   Name ").name == "New Name"


# ─────────────────────────────────────────────────────────────────────────────
# API keys stay out of lists
# ─────────────────────────────────────────────────────────────────────────────

def test_key_hint_shows_only_the_tail():
    assert key_hint("abcdefghijklmnop") == "…mnop"
    assert key_hint(None) is None


def test_list_rows_never_carry_the_key():
    tenant = Obj(id=7, name="Acme", created_at=None, api_key="SECRET-KEY-1234")
    row = mod._row(tenant, None)
    assert "api_key" not in row
    assert row["api_key_hint"] == "…1234"
    assert "SECRET" not in repr(row)


# ─────────────────────────────────────────────────────────────────────────────
# Creation provisions a usable organisation
# ─────────────────────────────────────────────────────────────────────────────

async def test_duplicate_name_is_refused(monkeypatch, audited):
    async def taken(db, name, except_id=None):
        return True

    monkeypatch.setattr(mod, "_name_taken", taken)
    db = FakeSession()
    with pytest.raises(HTTPException) as exc:
        await mod.create_tenant(_valid(), FakeRequest(), SUPER, db)
    assert exc.value.status_code == 409
    assert db.added == [] and db.commits == 0
    assert audited == []


async def test_email_used_anywhere_is_refused(monkeypatch, audited):
    async def free(db, name, except_id=None):
        return False

    monkeypatch.setattr(mod, "_name_taken", free)
    # First execute is the email lookup; returning a row means it's taken.
    db = FakeSession((42,))
    with pytest.raises(HTTPException) as exc:
        await mod.create_tenant(_valid(), FakeRequest(), SUPER, db)
    assert exc.value.status_code == 409
    assert "priya@acme.com" in exc.value.detail
    assert db.added == [] and db.commits == 0


async def test_creation_provisions_tenant_department_settings_and_admin(monkeypatch, audited):
    async def free(db, name, except_id=None):
        return False

    async def no_stats(db, tenant_id=None):
        return {}

    monkeypatch.setattr(mod, "_name_taken", free)
    monkeypatch.setattr(mod, "_stats", no_stats)
    db = FakeSession(None)  # email lookup: not taken

    out = await mod.create_tenant(_valid(department="Operations"), FakeRequest(), SUPER, db)

    kinds = [type(o).__name__ for o in db.added]
    assert kinds == ["Tenant", "Department", "Settings", "User"]
    tenant, dept, settings, admin = db.added
    assert dept.tenant_id == tenant.id and dept.department_name == "Operations"
    assert settings.tenant_id == tenant.id
    assert admin.role == "tenant_admin"
    assert admin.tenant_id == tenant.id and admin.dept_id == dept.department_id
    assert admin.email == "priya@acme.com"
    # Stored hashed, never as given.
    assert admin.password_hash and admin.password_hash != "Welcome2026"
    assert db.commits == 1

    # The key is returned once, here, and the row itself only carries a hint.
    assert out["api_key"] == tenant.api_key
    assert "api_key" not in out["tenant"]
    assert out["admin"]["email"] == "priya@acme.com"

    assert [c["action"] for c in audited] == ["organisation.created"]
    assert audited[0]["tenant_id"] == tenant.id
    assert "password" not in repr(audited[0]["details"]).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Deletion only when empty
# ─────────────────────────────────────────────────────────────────────────────

def test_blocker_sentence_lists_everything():
    msg = describe_blockers([
        {"table": "users", "label": "people", "count": 12},
        {"table": "devices", "label": "devices", "count": 2},
        {"table": "attendance_logs", "label": "attendance records", "count": 340},
    ])
    assert "12 people, 2 devices and 340 attendance records" in msg


async def test_delete_is_refused_while_the_organisation_holds_data(monkeypatch, audited):
    tenant = Obj(id=9, name="Northwind", api_key="k" * 32)

    async def get(db, tid):
        return tenant

    async def inventory(db, tid):
        return [{"table": "users", "label": "people", "count": 3}]

    monkeypatch.setattr(mod, "_get_tenant_or_404", get)
    monkeypatch.setattr(mod, "_inventory", inventory)
    db = FakeSession()

    with pytest.raises(HTTPException) as exc:
        await mod.delete_tenant(9, FakeRequest(), SUPER, db)

    assert exc.value.status_code == 409
    assert "3 people" in exc.value.detail
    assert db.deleted == []
    # Nothing destructive ran...
    assert not any("DELETE" in sql for sql, _ in db.executed)
    # ...but the attempt is on record, and committed so the refusal keeps it.
    assert [c["action"] for c in audited] == ["organisation.delete_refused"]
    assert audited[0]["result"] == "denied"
    assert db.commits == 1


async def test_empty_organisation_is_deleted_with_its_scaffolding(monkeypatch, audited):
    tenant = Obj(id=5, name="Typo Org", api_key="k" * 32)

    async def get(db, tid):
        return tenant

    async def inventory(db, tid):
        return []

    async def tables(db):
        return ["audit_log", "departments", "settings", "users", "vaults"]

    monkeypatch.setattr(mod, "_get_tenant_or_404", get)
    monkeypatch.setattr(mod, "_inventory", inventory)
    monkeypatch.setattr(mod, "_tenant_tables", tables)
    db = FakeSession()

    out = await mod.delete_tenant(5, FakeRequest(), SUPER, db)

    deletes = [sql for sql, _ in db.executed if sql.startswith("DELETE")]
    # Users before departments (users.dept_id references them); audit_log kept.
    assert deletes == [
        'DELETE FROM "vaults" WHERE tenant_id = :t',
        "DELETE FROM users WHERE tenant_id = :t AND role = 'tenant_admin'",
        'DELETE FROM "departments" WHERE tenant_id = :t',
        'DELETE FROM "settings" WHERE tenant_id = :t',
    ]
    assert db.deleted == [tenant]
    assert [c["action"] for c in audited] == ["organisation.deleted"]
    assert db.commits == 1
    assert "Typo Org" in out["message"]


async def test_inventory_ignores_history_and_scaffolding_but_counts_people():
    catalog = ["audit_log", "departments", "devices", "settings", "users"]

    class CatalogSession(FakeSession):
        async def execute(self, stmt, params=None):
            sql = str(stmt)
            self.executed.append((sql, params))
            if "information_schema" in sql:
                return FakeResult(catalog)
            if "FROM users" in sql:
                assert "role <> 'tenant_admin'" in sql
                return Obj(scalar_one=lambda: 4)
            if 'FROM "devices"' in sql:
                return Obj(scalar_one=lambda: 0)
            raise AssertionError(f"unexpected query: {sql}")

    db = CatalogSession()
    blockers = await mod._inventory(db, 1)
    assert blockers == [{"table": "users", "label": "people", "count": 4}]
    counted = [sql for sql, _ in db.executed if "information_schema" not in sql]
    # Two counts: people, devices. History and scaffolding are never counted.
    assert len(counted) == 2
    assert not any("audit_log" in sql or '"settings"' in sql or '"departments"' in sql
                   for sql in counted)


# ─────────────────────────────────────────────────────────────────────────────
# Key rotation
# ─────────────────────────────────────────────────────────────────────────────

async def test_rotation_issues_a_new_key_and_keeps_it_out_of_the_log(monkeypatch, audited):
    tenant = Obj(id=3, name="Harbour", api_key="old-key-0000")

    async def get(db, tid):
        return tenant

    monkeypatch.setattr(mod, "_get_tenant_or_404", get)
    db = FakeSession()

    out = await mod.reset_tenant_api_key(3, FakeRequest(), SUPER, db)

    assert tenant.api_key != "old-key-0000"
    assert out["new_api_key"] == tenant.api_key
    assert audited[0]["action"] == "organisation.api_key_rotated"
    assert tenant.api_key not in repr(audited[0])
    assert db.commits == 1
