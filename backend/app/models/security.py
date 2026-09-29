"""
Security models: configurable roles, permissions, MFA enrolment, step-up
assertions, and the append-only audit log.

Kept separate from domain.py deliberately — that module holds the attendance
and task domain, this one holds the access-control machinery. They share the
same declarative Base so Alembic sees one metadata.

`users.role` (the existing free-text column) is NOT removed. It still drives
the legacy checks in app/api/dependencies.py, and ripping it out would break
every existing route in one commit. Instead each legacy value is mirrored by a
seeded system role here, and new code reads permissions rather than the string.
Phase 3 or later can retire the column once nothing reads it.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.models.domain import Base

# ─────────────────────────────────────────────────────────────────────────────
# Roles and permissions
# ─────────────────────────────────────────────────────────────────────────────

class Role(Base):
    """
    A named bundle of permissions.

    System roles (is_system=True) are seeded and cannot be deleted or have their
    code changed — the application reasons about them by code. Custom roles are
    tenant-scoped and fully editable, which is the "configurable custom roles"
    requirement.

    tenant_id is NULL for system roles so they exist once globally rather than
    being duplicated per tenant.
    """

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    is_system = Column(Boolean, nullable=False, default=False)

    # Super Admin is the one role whose power is not expressed as a permission
    # list: it is implicit access to everything, by requirement. Flagged rather
    # than enumerated so nobody can accidentally create a second one by
    # assembling the right permissions.
    grants_all = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # A tenant may not have two roles with the same code; system roles
        # (tenant_id NULL) are globally unique because Postgres treats NULLs as
        # distinct, so a partial index handles that half.
        UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
        Index(
            "uq_role_system_code",
            "code",
            unique=True,
            postgresql_where=Column("tenant_id").is_(None),
        ),
    )


class Permission(Base):
    """
    One capability, identified by a stable dotted code (`credential.reveal`).

    Rows are seeded from app/core/permissions.py rather than created by users:
    a permission only means something if code checks for it, so inventing new
    ones at runtime would produce permissions that grant nothing.
    """

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(96), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)

    # True for permissions that expose secret material and therefore require a
    # fresh MFA assertion. Stored rather than hardcoded at the call site so the
    # rule is visible in the data and auditable.
    requires_step_up = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(
        Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("ix_role_permissions_role", "role_id"),
    )


class UserRole(Base):
    """
    Role assignment. A user may hold several roles; effective permission is the
    union, with deny-by-default when the union is empty.

    expires_at supports temporary elevation — granting someone an admin role for
    an incident without having to remember to remove it afterwards.
    """

    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)

    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        Index("ix_user_roles_user", "user_id"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# MFA and step-up
# ─────────────────────────────────────────────────────────────────────────────

class MfaCredential(Base):
    """
    An enrolled second factor. TOTP only for now; `kind` exists so WebAuthn can
    be added later without a migration to this table's shape.

    The TOTP secret is encrypted at rest with app/core/crypto.py. That is Fernet
    under GITHUB_ENC_KEY today — Phase 4 moves it under the KMS-backed envelope
    along with everything else. Recorded here so the dependency is not a
    surprise later.
    """

    __tablename__ = "mfa_credentials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    kind = Column(String(32), nullable=False, default="totp")
    secret_encrypted = Column(Text, nullable=False)
    label = Column(String(128), nullable=True)

    # Enrolment is two-step: create the secret, then prove possession before it
    # counts. An unconfirmed credential must never satisfy a step-up check,
    # otherwise enrolling is itself a bypass.
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Replay defence. TOTP codes stay valid for a whole window, so without
    # remembering the last accepted counter an intercepted code works twice.
    last_used_counter = Column(BigInteger, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_mfa_credentials_user", "user_id"),)


class StepUpAssertion(Base):
    """
    Proof that a user re-authenticated recently, for a specific purpose.

    Deliberately database-backed rather than a signed stateless token: a
    credential vault needs the ability to revoke an assertion the instant abuse
    is suspected, and a stateless token cannot be recalled. The cost is one
    indexed lookup per sensitive action, which is negligible next to a KMS
    round-trip.

    Only the SHA-256 of the token is stored. A leaked database row is then
    useless on its own.
    """

    __tablename__ = "step_up_assertions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    token_hash = Column(String(64), nullable=False, unique=True, index=True)

    # Binds the assertion to one login session. Without this, an assertion
    # obtained in one session would authorise a reveal in another — including a
    # session an attacker opened with a stolen refresh token.
    session_jti = Column(String(64), nullable=True, index=True)

    # What it authorises, e.g. "credential.reveal". An assertion minted for one
    # purpose must not unlock another.
    purpose = Column(String(96), nullable=False)

    mfa_method = Column(String(32), nullable=False, default="totp")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_step_up_user_purpose", "user_id", "purpose"),)


# ─────────────────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Append-only, hash-chained record of everything that matters.

    Append-only is enforced by the database grant, not by this class — see the
    migration, which revokes UPDATE and DELETE from the application role. A
    convention in Python is not a control; a revoked grant is.

    Tamper evidence: each row stores the hash of its predecessor, so altering
    any row breaks every hash after it. That only detects an attacker who
    cannot rewrite the whole table — see SECURITY.md §5.3. Anchoring the head
    externally is what makes this meaningful, and is tracked as decision 7.

    No column here ever holds secret material. Not the value, not a fragment,
    not its length, not a hash of it.
    """

    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True)

    # Position in the chain. Separate from id so the chain stays verifiable even
    # if the sequence ever skips (rollbacks consume sequence values).
    seq = Column(BigInteger, nullable=False, unique=True, index=True)

    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    tenant_id = Column(Integer, nullable=True, index=True)
    actor_id = Column(Integer, nullable=True, index=True)
    actor_role = Column(String(64), nullable=True)

    action = Column(String(96), nullable=False, index=True)
    target_type = Column(String(64), nullable=True)
    target_id = Column(String(64), nullable=True)

    result = Column(String(16), nullable=False)  # success | denied | error
    reason = Column(Text, nullable=True)

    source_ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    session_jti = Column(String(64), nullable=True)
    mfa_method = Column(String(32), nullable=True)

    # Structured extras. Callers are responsible for keeping secrets out; the
    # writer in app/core/audit.py screens known-dangerous keys as a backstop.
    details = Column(JSONB, nullable=True)

    prev_hash = Column(String(64), nullable=True)
    hash = Column(String(64), nullable=False)

    __table_args__ = (
        # The common queries: "what happened to this object" and "what did this
        # person do", both newest-first.
        Index("ix_audit_target", "target_type", "target_id", "occurred_at"),
        Index("ix_audit_actor_time", "actor_id", "occurred_at"),
        Index("ix_audit_tenant_time", "tenant_id", "occurred_at"),
    )
