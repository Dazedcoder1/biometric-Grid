"""
Admin oversight and password resets.

Both features let one person act on another's account, so the tests lean on
the refusals: who an admin may NOT reach, what is NOT revealed when a check
fails, what is NOT left behind after a reset.

Scope is tested through can_oversee directly — it is pure — and the routes are
called with fakes, since what matters is the decision each makes and the order
it does things in, not FastAPI's wiring.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import dependencies as deps_mod
from app.core.permissions import PermissionSet
from app.api.routes.common import accounts as accounts_mod
from app.api.routes.vault import oversight as oversight_mod
from app.core.security import verify_password
from app.services import oversight_service
from app.services.oversight_service import can_oversee


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def person(id, role, tenant_id=1, dept_id=10, name=None, **kw):
    return Obj(id=id, role=role, tenant_id=tenant_id, dept_id=dept_id,
               name=name or f"user{id}", email=f"u{id}@x.test", employee_code=None,
               is_active=True, must_change_password=False, password_hash="x", **kw)


TA = person(1, "tenant_admin", dept_id=None)
OA = person(2, "org_admin", dept_id=10)
EMP_SAME = person(3, "employee", dept_id=10)
EMP_OTHER_DEPT = person(4, "employee", dept_id=20)
OA_OTHER_DEPT = person(5, "org_admin", dept_id=20)
TA_PEER = person(6, "tenant_admin", dept_id=None)
EMP_OTHER_TENANT = person(7, "employee", tenant_id=2, dept_id=10)
SUPER = person(8, "super_admin", tenant_id=None, dept_id=None)


# ─────────────────────────────────────────────────────────────────────────────
# Scope
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("admin,target,expected", [
    # Tenant Admin: everyone below them in their organisation
    (TA, OA, True),
    (TA, EMP_SAME, True),
    (TA, EMP_OTHER_DEPT, True),
    (TA, OA_OTHER_DEPT, True),
    # ...but never a peer, never themselves, never another organisation
    (TA, TA_PEER, False),
    (TA, TA, False),
    (TA, EMP_OTHER_TENANT, False),
    # Org Admin: employees in their own department only
    (OA, EMP_SAME, True),
    (OA, EMP_OTHER_DEPT, False),
    (OA, OA_OTHER_DEPT, False),
    (OA, TA, False),
    (OA, EMP_OTHER_TENANT, False),
    # Nobody else reaches anyone
    (EMP_SAME, EMP_OTHER_DEPT, False),
    (EMP_SAME, OA, False),
    # A Super Admin with no organisation chosen reaches nobody
    (SUPER, EMP_SAME, False),
    (SUPER, TA, False),
])
def test_scope(admin, target, expected):
    assert can_oversee(admin, target) is expected


@pytest.mark.parametrize("target,expected", [
    (TA, True), (TA_PEER, True), (OA, True), (EMP_SAME, True), (EMP_OTHER_DEPT, True),
    # ...but only inside the organisation they are working in
    (EMP_OTHER_TENANT, False),
    (SUPER, False),                      # never themselves
])
def test_super_admin_reaches_everyone_in_the_chosen_organisation(target, expected):
    assert can_oversee(SUPER, target, tenant_id=1) is expected


def test_acting_organisation_is_ignored_for_everyone_but_super_admin():
    # A Tenant Admin cannot point themselves at another organisation.
    assert can_oversee(TA, EMP_OTHER_TENANT, tenant_id=2) is False


def test_org_admin_without_department_reaches_nobody():
    # Not "everyone else whose dept_id is also NULL".
    loose = person(9, "org_admin", dept_id=None)
    assert can_oversee(loose, person(10, "employee", dept_id=None)) is False


def test_scope_query_matches_can_oversee_for_unreachable_admins():
    assert oversight_service._scope_query(EMP_SAME) is None
    assert oversight_service._scope_query(SUPER) is None
    assert oversight_service._scope_query(person(9, "org_admin", dept_id=None)) is None


# ─────────────────────────────────────────────────────────────────────────────
# Fakes for the routes
# ─────────────────────────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return Obj()

    async def commit(self):
        self.commits += 1


class Ctx:
    def __init__(self, user, acting=None):
        self.user = user
        self.acting_tenant_id = acting if acting is not None else user.tenant_id
        self.permissions = PermissionSet(grants_all=user.role == "super_admin")

    def audit_kwargs(self):
        return {"tenant_id": self.user.tenant_id, "actor_id": self.user.id,
                "actor_role": self.user.role}


@pytest.fixture
def recorder(monkeypatch):
    """Capture audit rows, notifications and reveals, in the order they happen."""
    events = []

    async def record(db, **kw):
        events.append(("audit", kw["action"], kw))

    async def notify(db, **kw):
        events.append(("notify", kw["event_type"], kw))

    async def reveal(db, *, ctx, credential):
        events.append(("reveal", credential.id, {}))
        return {"secret": "s3cret", "notes": None, "version": 1}

    async def revoke_all(db, *, user_id):
        events.append(("revoke_step_up", user_id, {}))
        return 2

    monkeypatch.setattr(oversight_mod.audit, "record", record)
    monkeypatch.setattr(oversight_mod.notification_service, "notify_single_user", notify)
    monkeypatch.setattr(oversight_mod.svc, "reveal", reveal)
    monkeypatch.setattr(accounts_mod.mfa, "revoke_all_for_user", revoke_all)
    return events


def _with_people(monkeypatch, module, *people):
    by_id = {p.id: p for p in people}

    async def get_overseeable(db, admin, user_id, tenant_id=None):
        target = by_id.get(user_id)
        if not target or not can_oversee(admin, target, tenant_id):
            raise HTTPException(404, "Person not found.")
        return target

    monkeypatch.setattr(module.oversight, "get_overseeable", get_overseeable)


def _with_credential(monkeypatch, cred):
    async def get_credential(db, cid):
        if cid != cred.id:
            raise HTTPException(404, "Credential not found.")
        return cred

    monkeypatch.setattr(oversight_mod.svc, "get_credential", get_credential)


# ─────────────────────────────────────────────────────────────────────────────
# Reveal
# ─────────────────────────────────────────────────────────────────────────────

async def test_reveal_in_scope_audits_first_then_notifies_the_owner(monkeypatch, recorder):
    cred = Obj(id=50, name="Prod DB", owner_id=EMP_SAME.id, tenant_id=1)
    _with_credential(monkeypatch, cred)
    _with_people(monkeypatch, oversight_mod, EMP_SAME)
    db = FakeDB()

    out = await oversight_mod.oversight_reveal(50, Ctx(OA), db)

    assert out["secret"] == "s3cret"
    kinds = [e[0] for e in recorder]
    # The oversight row is written before anything is decrypted.
    assert kinds == ["audit", "reveal", "notify"]
    assert recorder[0][1] == "credential.revealed_by_admin"
    notice = recorder[2][2]
    assert notice["recipient_id"] == EMP_SAME.id
    assert "Prod DB" in notice["message"]
    assert db.commits == 1


async def test_reveal_out_of_scope_reveals_nothing_and_looks_like_404(monkeypatch, recorder):
    cred = Obj(id=51, name="Other dept", owner_id=EMP_OTHER_DEPT.id, tenant_id=1)
    _with_credential(monkeypatch, cred)
    _with_people(monkeypatch, oversight_mod, EMP_OTHER_DEPT)

    with pytest.raises(HTTPException) as exc:
        await oversight_mod.oversight_reveal(51, Ctx(OA), FakeDB())

    assert exc.value.status_code == 404
    assert exc.value.detail == "Credential not found."   # same as "doesn't exist"
    assert recorder == []


async def test_reveal_across_organisations_is_404_before_scope_is_even_checked(monkeypatch, recorder):
    cred = Obj(id=52, name="Elsewhere", owner_id=EMP_OTHER_TENANT.id, tenant_id=2)
    _with_credential(monkeypatch, cred)
    _with_people(monkeypatch, oversight_mod, EMP_OTHER_TENANT)

    with pytest.raises(HTTPException) as exc:
        await oversight_mod.oversight_reveal(52, Ctx(TA), FakeDB())
    assert exc.value.status_code == 404
    assert recorder == []


async def test_own_credential_goes_through_the_ordinary_reveal(monkeypatch, recorder):
    cred = Obj(id=53, name="Mine", owner_id=OA.id, tenant_id=1)
    _with_credential(monkeypatch, cred)

    with pytest.raises(HTTPException) as exc:
        await oversight_mod.oversight_reveal(53, Ctx(OA), FakeDB())
    assert exc.value.status_code == 400
    assert recorder == []


async def test_super_admin_without_an_organisation_is_asked_to_choose(monkeypatch, recorder):
    with pytest.raises(HTTPException) as exc:
        await oversight_mod.oversight_reveal(50, Ctx(SUPER), FakeDB())
    assert exc.value.status_code == 409
    assert recorder == []


async def test_super_admin_reveals_a_tenant_admins_secret_and_they_are_told(monkeypatch, recorder):
    cred = Obj(id=60, name="Billing", owner_id=TA.id, tenant_id=1)
    _with_credential(monkeypatch, cred)
    _with_people(monkeypatch, oversight_mod, TA)
    db = FakeDB()

    out = await oversight_mod.oversight_reveal(60, Ctx(SUPER, acting=1), db)

    assert out["secret"] == "s3cret"
    assert [e[0] for e in recorder] == ["audit", "reveal", "notify"]
    assert recorder[2][2]["recipient_id"] == TA.id


async def test_super_admin_changes_a_saved_password_audited_and_notified(monkeypatch, recorder):
    cred = Obj(id=61, name="Billing", owner_id=EMP_SAME.id, tenant_id=1)
    _with_credential(monkeypatch, cred)
    _with_people(monkeypatch, oversight_mod, EMP_SAME)

    async def impact(db, *, credential, action):
        return {"production_systems": 0, "systems": [], "summary": ""}

    async def rotate(db, *, ctx, credential, secret, notes=None):
        recorder.append(("rotate", credential.id, {"secret": secret}))
        return Obj(version=2)

    monkeypatch.setattr(oversight_mod.deps, "impact_of", impact)
    monkeypatch.setattr(oversight_mod.svc, "rotate", rotate)
    db = FakeDB()

    out = await oversight_mod.oversight_change_secret(
        61, oversight_mod.ChangeSecretIn(secret="n3w"), Ctx(SUPER, acting=1), db)

    assert out["version"] == 2
    assert [e[0] for e in recorder] == ["audit", "rotate", "notify"]
    assert recorder[0][1] == "credential.changed_by_admin"
    assert "n3w" not in repr(recorder[0]) and "n3w" not in repr(recorder[2])
    assert db.commits == 1


async def test_change_refused_until_production_impact_is_acknowledged(monkeypatch, recorder):
    cred = Obj(id=62, name="DB", owner_id=EMP_SAME.id, tenant_id=1)
    _with_credential(monkeypatch, cred)
    _with_people(monkeypatch, oversight_mod, EMP_SAME)

    async def impact(db, *, credential, action):
        return {"production_systems": 1, "systems": [{"name": "api"}], "summary": "1 system"}

    monkeypatch.setattr(oversight_mod.deps, "impact_of", impact)
    with pytest.raises(HTTPException) as exc:
        await oversight_mod.oversight_change_secret(
            62, oversight_mod.ChangeSecretIn(secret="x"), Ctx(SUPER, acting=1), FakeDB())
    assert exc.value.status_code == 409
    assert recorder == []


async def test_tenant_admin_may_look_but_not_change(monkeypatch, recorder):
    with pytest.raises(HTTPException) as exc:
        await oversight_mod.oversight_change_secret(
            50, oversight_mod.ChangeSecretIn(secret="x"), Ctx(TA), FakeDB())
    assert exc.value.status_code == 403
    assert recorder == []


async def test_super_admin_resets_a_tenant_admins_sign_in_password(monkeypatch, recorder):
    target = person(6, "tenant_admin", dept_id=None)
    _with_people(monkeypatch, accounts_mod, target)
    out = await accounts_mod.reset_password(6, None, Ctx(SUPER, acting=1), FakeDB())
    assert target.must_change_password is True
    assert accounts_mod.password_problem(out["temporary_password"]) is None


# ─────────────────────────────────────────────────────────────────────────────
# Viewing someone's list
# ─────────────────────────────────────────────────────────────────────────────

async def test_viewing_someone_elses_list_is_audited_but_own_is_not(monkeypatch, recorder):
    async def creds(db, owner_id):
        return []

    monkeypatch.setattr(oversight_mod.oversight, "credentials_of", creds)
    _with_people(monkeypatch, oversight_mod, EMP_SAME)

    await oversight_mod.oversight_credentials(OA.id, Ctx(OA), FakeDB())
    assert recorder == []

    await oversight_mod.oversight_credentials(EMP_SAME.id, Ctx(OA), FakeDB())
    assert [e[1] for e in recorder] == ["vault.oversight_viewed"]


# ─────────────────────────────────────────────────────────────────────────────
# Password reset
# ─────────────────────────────────────────────────────────────────────────────

def test_generated_passwords_meet_the_policy_and_differ():
    seen = {accounts_mod.generate_temporary_password() for _ in range(50)}
    assert len(seen) == 50
    for pw in seen:
        assert accounts_mod.password_problem(pw) is None
        assert not set(pw) & set("0O1lI")


@pytest.mark.parametrize("weak", ["short1A", "alllowercase1", "ALLUPPER1", "NoDigitsHere"])
def test_weak_supplied_passwords_are_refused(weak):
    with pytest.raises(ValidationError):
        accounts_mod.ResetIn(temporary_password=weak)


async def test_reset_sets_temp_password_forces_change_and_signs_them_out(monkeypatch, recorder):
    target = person(3, "employee", dept_id=10)
    _with_people(monkeypatch, accounts_mod, target)
    monkeypatch.setattr(accounts_mod.audit, "record", oversight_mod.audit.record)
    monkeypatch.setattr(accounts_mod.notification_service, "notify_single_user",
                        oversight_mod.notification_service.notify_single_user)
    db = FakeDB()

    out = await accounts_mod.reset_password(3, None, Ctx(OA), db)

    temp = out["temporary_password"]
    assert accounts_mod.password_problem(temp) is None
    assert verify_password(temp, target.password_hash)
    assert target.must_change_password is True
    # Every existing session is ended: refresh tokens and step-up assertions.
    assert any("UPDATE refresh_tokens SET is_revoked = TRUE" in sql for sql, _ in db.executed)
    assert ("revoke_step_up", 3, {}) in recorder
    # Audited and notified — and the password is in neither.
    audit_rows = [e for e in recorder if e[0] == "audit"]
    assert [a[1] for a in audit_rows] == ["user.password_reset"]
    assert temp not in repr(recorder)
    assert db.commits == 1


async def test_reset_out_of_scope_changes_nothing(monkeypatch, recorder):
    target = person(4, "employee", dept_id=20)
    original_hash = target.password_hash
    _with_people(monkeypatch, accounts_mod, target)
    db = FakeDB()

    with pytest.raises(HTTPException) as exc:
        await accounts_mod.reset_password(4, None, Ctx(OA), db)

    assert exc.value.status_code == 404
    assert target.password_hash == original_hash
    assert target.must_change_password is False
    assert db.executed == [] and db.commits == 0


async def test_reset_cannot_target_yourself():
    with pytest.raises(HTTPException) as exc:
        await accounts_mod.reset_password(OA.id, None, Ctx(OA), FakeDB())
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# The forced change
# ─────────────────────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, user):
        self._u = user

    def scalars(self):
        return self

    def first(self):
        return self._u


class _UserDB:
    def __init__(self, user):
        self._u = user

    async def execute(self, stmt):
        return _Result(self._u)


def _request(path):
    return Obj(url=Obj(path=path))


async def test_temporary_password_blocks_everything_but_changing_it(monkeypatch):
    user = person(3, "employee")
    user.must_change_password = True
    monkeypatch.setattr(deps_mod, "decode_token", lambda t: {"type": "access", "user_id": 3})

    with pytest.raises(HTTPException) as exc:
        await deps_mod.get_current_user(_request("/api/vault/credentials"), "tok", _UserDB(user))
    assert exc.value.status_code == 403
    assert exc.value.headers == {"X-Password-Change-Required": "true"}

    for path in ("/api/auth/change-password", "/api/employee/profile/change-password"):
        assert await deps_mod.get_current_user(_request(path), "tok", _UserDB(user)) is user


async def test_normal_accounts_are_unaffected(monkeypatch):
    user = person(3, "employee")
    monkeypatch.setattr(deps_mod, "decode_token", lambda t: {"type": "access", "user_id": 3})
    assert await deps_mod.get_current_user(_request("/api/vault/credentials"), "tok", _UserDB(user)) is user
