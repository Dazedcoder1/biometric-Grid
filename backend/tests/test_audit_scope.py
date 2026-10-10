"""
Who can read which audit entries, and who an entry says did it.

scope_conditions is the one rule behind the log, the action filter, the
summary strip and the CSV export. It is compiled to SQL and inspected here —
there is no database in the test run — so these pin what each role's query
contains, which is what decides what they see.

resolve_actor is how routes that only know an organisation (Tenant Admin
routes resolve a Tenant, not a person) name who acted. Its failure mode is
naming the wrong person: /tenant-login tokens put the tenant's id in
user_id, so a naive lookup would attribute API-key actions to whichever user
happens to share that number.
"""

from __future__ import annotations

import pytest

from app.api.routes.vault.activity import scope_conditions
from app.core import activity
from app.core.permissions import PermissionSet


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def ctx(role, dept=10, tenant=1, grants_all=False, id=5):
    return Obj(user=Obj(id=id, role=role, dept_id=dept, tenant_id=tenant),
               permissions=PermissionSet(grants_all=grants_all))


def sql(conditions) -> str:
    return " AND ".join(
        str(c.compile(compile_kwargs={"literal_binds": True})) for c in conditions
    )


def test_super_admin_reads_everything():
    assert scope_conditions(ctx("super_admin", None, None, grants_all=True)) == []


def test_tenant_admin_reads_their_organisation_only():
    q = sql(scope_conditions(ctx("tenant_admin", None)))
    assert "audit_log.tenant_id = 1" in q
    assert "dept_id" not in q            # no department narrowing


def test_org_admin_is_narrowed_to_their_department():
    q = sql(scope_conditions(ctx("org_admin", 10)))
    assert "audit_log.tenant_id = 1" in q
    # by someone in the department
    assert "audit_log.actor_id IN" in q and "users.dept_id = 10" in q
    # about the department's people, credentials, systems, leave, tasks
    for kind in ("user", "credential", "system", "leave", "task"):
        assert f"audit_log.target_type = '{kind}'" in q
    assert "systems.department_id = 10" in q
    # or the department itself
    assert "audit_log.target_type = 'department'" in q and "audit_log.target_id = '10'" in q
    # never another department
    assert "dept_id = 20" not in q


def test_no_department_means_only_your_own_actions():
    q = sql(scope_conditions(ctx("org_admin", None, id=42)))
    assert "audit_log.actor_id = 42" in q
    assert "target_type" not in q


def test_every_reader_uses_the_same_rule():
    """The log, filter, export and summary must not disagree about scope."""
    import inspect
    from app.api.routes.vault import activity as mod
    for fn in (mod.audit_log, mod.known_actions, mod.export_csv, mod.summary):
        src = inspect.getsource(fn)
        assert "scope_conditions(ctx" in src, fn.__name__
        assert "AuditLog.tenant_id == ctx.user.tenant_id" not in src, fn.__name__


# ─── who did it ──────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, v):
        self._v = v

    def scalars(self):
        return self

    def first(self):
        return self._v


class _DB:
    def __init__(self, user):
        self._u = user

    async def execute(self, _stmt):
        return _Result(self._u)


def _req(headers):
    return Obj(headers={k.lower(): v for k, v in headers.items()})


@pytest.fixture
def token(monkeypatch):
    def use(payload):
        monkeypatch.setattr(activity, "decode_token", lambda t: payload)
    return use


async def test_bearer_naming_a_member_of_this_organisation_is_that_person(token):
    token({"user_id": 7, "jti": "j1"})
    member = Obj(id=7, role="tenant_admin", tenant_id=1)
    assert await activity.resolve_actor(_DB(member), _req({"Authorization": "Bearer x"}), 1) == (7, "tenant_admin", "j1")


async def test_tenant_login_token_naming_nobody_real_is_the_api_key(token):
    # user_id carries the tenant id; the user with that id belongs elsewhere.
    token({"user_id": 1, "jti": "j2"})
    stranger = Obj(id=1, role="employee", tenant_id=99)
    assert await activity.resolve_actor(_DB(stranger), _req({"Authorization": "Bearer x"}), 1) == (None, "api_key", None)


async def test_super_admin_acting_in_an_organisation_is_named(token):
    token({"user_id": 3, "jti": "j3"})
    sa = Obj(id=3, role="super_admin", tenant_id=None)
    assert await activity.resolve_actor(_DB(sa), _req({"Authorization": "Bearer x"}), 1) == (3, "super_admin", "j3")


async def test_api_key_header_has_no_person():
    assert await activity.resolve_actor(_DB(None), _req({"X-API-Key": "k"}), 1) == (None, "api_key", None)


async def test_log_never_carries_the_key_itself(monkeypatch):
    rows = []

    async def record(db, **kw):
        rows.append(kw)

    monkeypatch.setattr(activity.audit, "record", record)
    await activity.log(_DB(None), Obj(headers={"x-api-key": "SECRET-KEY"}, client=None),
                       action="device.created", tenant_id=1, anonymous="api_key")
    assert "SECRET-KEY" not in repr(rows)
    assert rows[0]["actor_role"] == "api_key" and rows[0]["actor_id"] is None
