"""
Who sees which systems on the dependency map, and who may move them.

The Production team sees production's systems, Testing sees testing's, both
see the shared ones, and the Tenant Admin sees all of it. These pin that rule
and its edges — nobody without a department sees "everything with no
department", an Org Admin cannot move a system into or out of someone else's
department, and a link cannot be deleted from outside its organisation.

Scope.sees is pure and tested directly. The SQL form (Scope.clause) is
compiled and inspected rather than run, since there is no database here; the
two must describe the same rule, and the test says which clauses each holds.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.credentials import System
from app.services import dependency_service as deps
from app.services.dependency_service import Scope, scope_for


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


PROD, TEST = 10, 20

def user(role, dept=PROD, tenant=1, id=1):
    return Obj(id=id, role=role, dept_id=dept, tenant_id=tenant)


def system(dept, tenant=1, id=100, name="api", env="production"):
    return Obj(id=id, tenant_id=tenant, department_id=dept, name=name, environment=env)


PROD_API = system(PROD, id=1)
TEST_API = system(TEST, id=2)
SHARED_VPN = system(None, id=3, name="vpn")
OTHER_ORG = system(PROD, tenant=2, id=4)


# ─── who sees what ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("who,expected", [
    # Production team: their own systems and shared, not Testing's
    (user("employee", PROD), {1, 3}),
    (user("org_admin", PROD), {1, 3}),
    # Testing team: the mirror image
    (user("employee", TEST), {2, 3}),
    (user("org_admin", TEST), {2, 3}),
    # Tenant Admin: everything in the organisation
    (user("tenant_admin", None), {1, 2, 3}),
    # No department: shared only — never "everything with no department"
    (user("employee", None), {3}),
])
def test_visibility(who, expected):
    scope = scope_for(who)
    seen = {s.id for s in (PROD_API, TEST_API, SHARED_VPN, OTHER_ORG) if scope.sees(s)}
    assert seen == expected


def test_nobody_sees_another_organisation():
    for role in ("employee", "org_admin", "tenant_admin"):
        assert scope_for(user(role)).sees(OTHER_ORG) is False


def test_super_admin_grants_all_sees_every_department_of_its_tenant():
    assert scope_for(user("super_admin", None), grants_all=True).all_departments is True


def test_sql_clause_carries_the_same_rule():
    def sql(scope):
        return str(scope.clause().compile(compile_kwargs={"literal_binds": True}))

    prod = sql(scope_for(user("employee", PROD)))
    assert "systems.tenant_id = 1" in prod
    assert "systems.department_id IS NULL" in prod
    assert "systems.department_id = 10" in prod

    no_dept = sql(scope_for(user("employee", None)))
    assert "systems.department_id IS NULL" in no_dept
    assert "systems.department_id =" not in no_dept

    admin = sql(scope_for(user("tenant_admin", None)))
    assert "department_id" not in admin
    assert "systems.tenant_id = 1" in admin


# ─── moving systems ──────────────────────────────────────────────────────────

class FakeDB:
    """Answers queued results in order; records adds."""

    def __init__(self, *results):
        self.results = list(results)

    async def execute(self, stmt, params=None):
        value = self.results.pop(0) if self.results else None
        return Obj(first=lambda: value, scalars=lambda: Obj(first=lambda: value))


class Ctx:
    def __init__(self, u):
        self.user = u

    def audit_kwargs(self):
        return {"tenant_id": self.user.tenant_id, "actor_id": self.user.id}


@pytest.fixture
def audits(monkeypatch):
    rows = []

    async def record(db, **kw):
        rows.append(kw)

    monkeypatch.setattr(deps.audit, "record", record)
    return rows


async def _move(monkeypatch, who, sys_obj, target, *, dept_exists=True, clash=False):
    scope = scope_for(who)

    async def visible(db, *, scope, system_id):
        if not scope.sees(sys_obj):
            raise HTTPException(404, "System not found.")
        return sys_obj

    monkeypatch.setattr(deps, "get_visible_system", visible)
    # Queue: department-exists check (only when a department is named), then
    # the clash check.
    queued = []
    if target is not None:
        queued.append((target,) if dept_exists else None)
    queued.append((99,) if clash else None)
    return await deps.move_system(FakeDB(*queued), ctx=Ctx(who), scope=scope,
                                  system_id=sys_obj.id, department_id=target)


async def test_org_admin_can_share_their_own_system(monkeypatch, audits):
    s = system(PROD, id=1)
    await _move(monkeypatch, user("org_admin", PROD), s, None)
    assert s.department_id is None
    assert audits[0]["action"] == "system.department_changed"


async def test_org_admin_can_claim_a_shared_system(monkeypatch, audits):
    s = system(None, id=3)
    await _move(monkeypatch, user("org_admin", PROD), s, PROD)
    assert s.department_id == PROD


async def test_org_admin_cannot_move_into_another_department(monkeypatch, audits):
    s = system(PROD, id=1)
    with pytest.raises(HTTPException) as exc:
        await _move(monkeypatch, user("org_admin", PROD), s, TEST)
    assert exc.value.status_code == 403
    assert s.department_id == PROD and audits == []


async def test_org_admin_cannot_touch_another_departments_system(monkeypatch, audits):
    s = system(TEST, id=2)
    with pytest.raises(HTTPException) as exc:
        await _move(monkeypatch, user("org_admin", PROD), s, None)
    assert exc.value.status_code == 404
    assert s.department_id == TEST and audits == []


async def test_tenant_admin_can_move_between_any_departments(monkeypatch, audits):
    s = system(PROD, id=1)
    await _move(monkeypatch, user("tenant_admin", None), s, TEST)
    assert s.department_id == TEST


async def test_department_must_be_in_the_organisation(monkeypatch, audits):
    s = system(PROD, id=1)
    with pytest.raises(HTTPException) as exc:
        await _move(monkeypatch, user("tenant_admin", None), s, 777, dept_exists=False)
    assert exc.value.status_code == 404
    assert s.department_id == PROD


async def test_name_clash_in_destination_is_a_clear_409(monkeypatch, audits):
    s = system(PROD, id=1)
    with pytest.raises(HTTPException) as exc:
        await _move(monkeypatch, user("tenant_admin", None), s, TEST, clash=True)
    assert exc.value.status_code == 409
    assert "already has a system called" in exc.value.detail
    assert s.department_id == PROD


# ─── unlinking ───────────────────────────────────────────────────────────────

async def test_unlink_outside_scope_is_404():
    """get_dependency joins on organisation and scope — no row, no delete."""
    with pytest.raises(HTTPException) as exc:
        await deps.get_dependency(FakeDB(None), scope=scope_for(user("employee", PROD)),
                                  dependency_id=5)
    assert exc.value.status_code == 404


def test_get_dependency_query_checks_organisation_and_scope():
    import inspect
    src = inspect.getsource(deps.get_dependency)
    assert "Credential.tenant_id == scope.tenant_id" in src
    assert "scope.clause()" in src


# ─── impact still shows everything ───────────────────────────────────────────

def test_impact_marks_but_does_not_hide_other_departments():
    """
    Rotation impact must list every system the credential feeds — hiding a
    production system from the person about to rotate its password is how
    outages happen. It labels them instead.
    """
    import inspect
    src = inspect.getsource(deps.impact_of)
    assert "other_department" in src
    assert "scope.clause()" not in src


def test_model_uniqueness_includes_department():
    names = {ix.name for ix in System.__table__.indexes}
    assert "uq_system_tenant_dept_name_env" in names
