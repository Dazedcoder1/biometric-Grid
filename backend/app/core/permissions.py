"""
The permission catalogue and the deny-by-default resolver.

A permission code only means something if code checks for it, so the catalogue
lives here in source rather than being user-creatable. The seeder mirrors it
into the `permissions` table; anything in the table but not here is dead.

Phase 2 defines the access-control machinery. Codes for objects that do not
exist yet (vaults, racks, credentials — Phase 3 and 5) are declared now so the
vocabulary is settled before anything depends on it, but nothing enforces them
until those features land.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    description: str
    # True when exercising it exposes secret material, and a fresh MFA
    # assertion is therefore required. See app/core/mfa.py.
    requires_step_up: bool = False


CATALOGUE: tuple[PermissionDef, ...] = (
    # ─── Roles and access control ────────────────────────────────────────────
    PermissionDef("role.view", "List roles and their permissions"),
    PermissionDef("role.manage", "Create, edit and delete custom roles"),
    PermissionDef("role.assign", "Grant and revoke roles for users"),

    # ─── Vaults (Phase 5) ────────────────────────────────────────────────────
    PermissionDef("vault.view", "See vaults shared with you"),
    PermissionDef("vault.manage", "Create and configure vaults"),

    # ─── Racks (Phase 5) ─────────────────────────────────────────────────────
    PermissionDef("rack.view", "See racks inside an accessible vault"),
    PermissionDef("rack.manage", "Create, rename and delete racks"),

    # ─── Credentials (Phase 5) ───────────────────────────────────────────────
    PermissionDef("credential.view", "See that a credential exists, and its metadata"),
    PermissionDef("credential.create", "Add a new credential"),
    PermissionDef("credential.edit", "Change metadata, and rotate the secret"),
    PermissionDef("credential.delete", "Delete a credential"),
    PermissionDef(
        "credential.reveal",
        "Decrypt and see a secret value",
        requires_step_up=True,
    ),

    # ─── Sharing (Phase 5) ───────────────────────────────────────────────────
    PermissionDef("share.view", "See who a credential is shared with"),
    PermissionDef("share.grant", "Share a credential with another user or team"),
    PermissionDef("share.revoke", "Withdraw a share"),

    # ─── Audit ───────────────────────────────────────────────────────────────
    PermissionDef("audit.view", "Read the audit log"),
    PermissionDef("audit.verify", "Run the hash-chain verification pass"),
)

BY_CODE: dict[str, PermissionDef] = {p.code: p for p in CATALOGUE}

#: Codes whose use requires a fresh step-up assertion.
STEP_UP_REQUIRED: frozenset[str] = frozenset(
    p.code for p in CATALOGUE if p.requires_step_up
)


# ─────────────────────────────────────────────────────────────────────────────
# Seeded system roles
# ─────────────────────────────────────────────────────────────────────────────
# Each mirrors one of the existing `users.role` strings so legacy accounts keep
# working unchanged. `super_admin` carries grants_all rather than a permission
# list — see Role.grants_all for why.

SYSTEM_ROLES: dict[str, dict] = {
    "super_admin": {
        "name": "Super Admin",
        "description": "Unrestricted access to every tenant. Every action is audited.",
        "grants_all": True,
        "permissions": (),
    },
    "tenant_admin": {
        "name": "Tenant Admin",
        "description": "Administers one organisation.",
        "grants_all": False,
        "permissions": (
            "role.view", "role.manage", "role.assign",
            "vault.view", "vault.manage",
            "rack.view", "rack.manage",
            "credential.view", "credential.create", "credential.edit", "credential.delete",
            "share.view", "share.grant", "share.revoke",
            "audit.view",
            # Deliberately NOT credential.reveal. A Tenant Admin authenticating
            # by long-lived API key has no user identity and no second factor;
            # see ARCHITECTURE.md §5. Reveal is granted to people, not keys.
        ),
    },
    "org_admin": {
        "name": "Organisation Admin",
        "description": "Day-to-day administration within an organisation.",
        "grants_all": False,
        "permissions": (
            "vault.view", "rack.view", "rack.manage",
            "credential.view", "credential.create", "credential.edit",
            "credential.reveal",
            "share.view", "share.grant", "share.revoke",
        ),
    },
    "employee": {
        "name": "Employee",
        "description": "Access to their own vault and anything shared with them.",
        "grants_all": False,
        "permissions": (
            "vault.view", "rack.view",
            "credential.view", "credential.create", "credential.edit",
            "credential.reveal",
            "share.view",
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Resolution
# ─────────────────────────────────────────────────────────────────────────────

class PermissionSet:
    """
    A user's effective permissions, resolved once per request.

    Deny-by-default: `has()` returns False for anything not explicitly granted,
    including codes that do not exist. A typo in a permission check therefore
    denies access rather than granting it — the safe direction to fail.
    """

    __slots__ = ("_codes", "_grants_all", "role_codes")

    def __init__(
        self,
        codes: Iterable[str] = (),
        *,
        grants_all: bool = False,
        role_codes: Iterable[str] = (),
    ) -> None:
        self._codes = frozenset(codes)
        self._grants_all = bool(grants_all)
        self.role_codes = tuple(role_codes)

    @property
    def grants_all(self) -> bool:
        return self._grants_all

    def has(self, code: str) -> bool:
        if self._grants_all:
            return True
        return code in self._codes

    def has_any(self, *codes: str) -> bool:
        return any(self.has(c) for c in codes)

    def has_all(self, *codes: str) -> bool:
        return all(self.has(c) for c in codes)

    def as_list(self) -> list[str]:
        """Sorted codes, for API responses and debugging.

        A grants_all set reports the full catalogue rather than a wildcard, so
        the client renders real capabilities instead of special-casing '*'.
        """
        if self._grants_all:
            return sorted(BY_CODE)
        return sorted(self._codes)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self._grants_all:
            return "<PermissionSet grants_all>"
        return f"<PermissionSet {len(self._codes)} codes>"


#: The permission set for an unauthenticated or unrecognised caller. Empty and
#: not grants_all, so every check fails.
DENY_ALL = PermissionSet()
