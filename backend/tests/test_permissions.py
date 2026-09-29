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


def test_tenant_admin_cannot_reveal():
    """A long-lived API key with no second factor must not decrypt secrets.

    ARCHITECTURE.md §5. Tenant Admin authenticates by API key, which has no
    user identity to step up. Managing credentials is fine; reading them is not.
    """
    assert "credential.reveal" not in SYSTEM_ROLES["tenant_admin"]["permissions"]


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
