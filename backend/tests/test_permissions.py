"""
Permission resolution, with the emphasis on denial.

These run against PermissionSet directly — no database, no event loop. The
resolver is where an authorisation bug would live, and it is worth testing in
isolation from everything that could mask one.
"""

from __future__ import annotations

import pytest

from app.core.permissions import (
    BY_CODE,
    CATALOGUE,
    DENY_ALL,
    STEP_UP_REQUIRED,
    SYSTEM_ROLES,
    PermissionSet,
)

# ─── deny-by-default ─────────────────────────────────────────────────────────

def test_empty_set_denies_everything():
    ps = PermissionSet()
    for perm in CATALOGUE:
        assert ps.has(perm.code) is False


def test_deny_all_constant_denies_everything():
    for perm in CATALOGUE:
        assert DENY_ALL.has(perm.code) is False


def test_unknown_code_is_denied_not_granted():
    """A typo in a permission check must fail closed.

    This is the single most important test here. If `has()` returned True for
    unrecognised codes, every misspelled guard would be an open door.
    """
    ps = PermissionSet(["credential.view"])
    assert ps.has("credential.reveal") is False
    assert ps.has("credential.reveel") is False     # typo
    assert ps.has("") is False
    assert ps.has("*") is False
    assert ps.has("admin") is False


def test_granted_code_is_allowed():
    ps = PermissionSet(["credential.view", "credential.create"])
    assert ps.has("credential.view") is True
    assert ps.has("credential.create") is True
    assert ps.has("credential.delete") is False


# ─── grants_all ──────────────────────────────────────────────────────────────

def test_grants_all_allows_every_catalogued_permission():
    ps = PermissionSet(grants_all=True)
    for perm in CATALOGUE:
        assert ps.has(perm.code) is True


def test_grants_all_also_allows_unknown_codes():
    """Super Admin is unrestricted by requirement, including future codes.

    Documenting the behaviour rather than endorsing it: a permission added
    later is granted to Super Admin without anyone deciding so. That is what
    "sees everything" means, and it is why every such access is audited
    separately.
    """
    ps = PermissionSet(grants_all=True)
    assert ps.has("something.invented.later") is True


def test_grants_all_reports_full_catalogue_not_wildcard():
    ps = PermissionSet(grants_all=True)
    assert ps.as_list() == sorted(BY_CODE)
    assert "*" not in ps.as_list()


# ─── combinators ─────────────────────────────────────────────────────────────

def test_has_any():
    ps = PermissionSet(["credential.view"])
    assert ps.has_any("credential.view", "credential.delete") is True
    assert ps.has_any("credential.delete", "role.manage") is False
    assert ps.has_any() is False


def test_has_all():
    ps = PermissionSet(["credential.view", "credential.edit"])
    assert ps.has_all("credential.view", "credential.edit") is True
    assert ps.has_all("credential.view", "credential.delete") is False
    assert ps.has_all() is True          # vacuous truth, matches all()


# ─── catalogue integrity ─────────────────────────────────────────────────────

def test_catalogue_codes_are_unique():
    codes = [p.code for p in CATALOGUE]
    assert len(codes) == len(set(codes))


def test_reveal_requires_step_up():
    assert "credential.reveal" in STEP_UP_REQUIRED
    assert BY_CODE["credential.reveal"].requires_step_up is True


def test_only_secret_exposing_permissions_require_step_up():
    """Step-up should gate secret exposure, not ordinary administration.

    Over-applying it trains users to approve prompts reflexively, which is how
    MFA fatigue attacks succeed.
    """
    assert STEP_UP_REQUIRED == {"credential.reveal"}


def test_system_roles_reference_real_permissions():
    for role_code, spec in SYSTEM_ROLES.items():
        for code in spec["permissions"]:
            assert code in BY_CODE, f"{role_code} references unknown permission {code}"


def test_only_super_admin_grants_all():
    granting = [c for c, s in SYSTEM_ROLES.items() if s["grants_all"]]
    assert granting == ["super_admin"]


def test_reveal_is_gated_by_step_up_not_by_role():
    """
    This replaces an earlier assertion that Tenant Admin must NOT hold
    credential.reveal. That rule existed because the only way to be a Tenant
    Admin was a long-lived API key: no user identity to name in the audit log,
    and nothing that could enrol a second factor. Tenant Admins now sign in
    with a password and enrol an authenticator, so the premise is gone.

    What still protects secrets is the mechanism, not the role list: reveal
    requires a fresh step-up assertion bound to a user and a session, which an
    API-key caller cannot produce. Asserting that here rather than re-asserting
    a role's contents keeps the test pointed at the control that does the work.
    """
    assert "credential.reveal" in STEP_UP_REQUIRED

    revealing = [
        code for code, spec in SYSTEM_ROLES.items()
        if not spec["grants_all"] and "credential.reveal" in spec["permissions"]
    ]
    assert revealing, "no role can reveal a secret — the vault would be write-only"
    for code in revealing:
        assert code != "super_admin"


def test_audit_verify_is_operator_only():
    """
    verify_chain walks the whole chain across every tenant, so its result
    discloses the volume and head hash of other organisations' activity. Until
    the pass can be scoped per tenant, no tenant-level role may run it.

    If this fails because verification became tenant-scoped, grant the
    permission and delete this test — do not widen it to allow the leak.
    """
    for code, spec in SYSTEM_ROLES.items():
        if spec["grants_all"]:
            continue
        assert "audit.verify" not in spec["permissions"], (
            f"{code} can verify the global hash chain, which spans tenants"
        )


def test_roles_that_can_act_can_also_read_the_record():
    """
    A role able to reveal secrets or grant access should be able to read the
    log of those actions. Org Admin held credential.reveal and share.grant but
    not audit.view, so the sidebar linked it to a page where every request
    returned 403 — and, worse, it could take the actions without being able to
    see them recorded.
    """
    for code, spec in SYSTEM_ROLES.items():
        if spec["grants_all"]:
            continue
        perms = set(spec["permissions"])
        if perms & {"credential.reveal", "share.grant"} and "rack.manage" in perms:
            assert "audit.view" in perms, (
                f"{code} can reveal or share but cannot read the audit log"
            )


def test_employee_cannot_manage_roles():
    perms = SYSTEM_ROLES["employee"]["permissions"]
    assert "role.manage" not in perms
    assert "role.assign" not in perms
    assert "credential.delete" not in perms


def test_no_role_has_duplicate_permissions():
    for role_code, spec in SYSTEM_ROLES.items():
        perms = spec["permissions"]
        assert len(perms) == len(set(perms)), f"{role_code} lists a permission twice"


@pytest.mark.parametrize("role_code", sorted(SYSTEM_ROLES))
def test_non_super_admin_roles_are_not_empty(role_code):
    spec = SYSTEM_ROLES[role_code]
    if spec["grants_all"]:
        return
    assert spec["permissions"], f"{role_code} grants nothing at all"
