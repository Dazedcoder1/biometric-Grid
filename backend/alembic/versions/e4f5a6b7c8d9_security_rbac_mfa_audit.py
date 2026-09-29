"""Phase 2: configurable roles, permissions, MFA, step-up, audit log

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-29

Creates the access-control machinery. No credential or vault tables here —
those are Phase 3.

Two things in this migration are not ordinary DDL and deserve attention:

1. The `audit_log` grant revocation. Append-only is enforced by the database
   refusing UPDATE and DELETE to the application role, not by discipline in
   Python. It is wrapped in a check because the role name varies by
   environment (Neon uses `neondb_owner`), and a missing role must not fail
   the migration — it must warn loudly instead.

2. Seeding. Permissions and system roles are data the code depends on: a
   permission code nothing checks grants nothing, and a missing system role
   breaks the legacy-role bridge in deps_security.load_permissions.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


# Mirrors app/core/permissions.CATALOGUE. Kept literal rather than imported:
# a migration must reproduce the state of the world at the time it was written,
# and importing application code makes it change meaning when that code changes.
PERMISSIONS = [
    ("role.view", "List roles and their permissions", False),
    ("role.manage", "Create, edit and delete custom roles", False),
    ("role.assign", "Grant and revoke roles for users", False),
    ("vault.view", "See vaults shared with you", False),
    ("vault.manage", "Create and configure vaults", False),
    ("rack.view", "See racks inside an accessible vault", False),
    ("rack.manage", "Create, rename and delete racks", False),
    ("credential.view", "See that a credential exists, and its metadata", False),
    ("credential.create", "Add a new credential", False),
    ("credential.edit", "Change metadata, and rotate the secret", False),
    ("credential.delete", "Delete a credential", False),
    ("credential.reveal", "Decrypt and see a secret value", True),
    ("share.view", "See who a credential is shared with", False),
    ("share.grant", "Share a credential with another user or team", False),
    ("share.revoke", "Withdraw a share", False),
    ("audit.view", "Read the audit log", False),
    ("audit.verify", "Run the hash-chain verification pass", False),
]

SYSTEM_ROLES = [
    ("super_admin", "Super Admin",
     "Unrestricted access to every tenant. Every action is audited.", True, []),
    ("tenant_admin", "Tenant Admin", "Administers one organisation.", False, [
        "role.view", "role.manage", "role.assign",
        "vault.view", "vault.manage", "rack.view", "rack.manage",
        "credential.view", "credential.create", "credential.edit", "credential.delete",
        "share.view", "share.grant", "share.revoke", "audit.view",
    ]),
    ("org_admin", "Organisation Admin",
     "Day-to-day administration within an organisation.", False, [
         "vault.view", "rack.view", "rack.manage",
         "credential.view", "credential.create", "credential.edit",
         "credential.reveal", "share.view", "share.grant", "share.revoke",
     ]),
    ("employee", "Employee",
     "Access to their own vault and anything shared with them.", False, [
         "vault.view", "rack.view",
         "credential.view", "credential.create", "credential.edit",
         "credential.reveal", "share.view",
     ]),
]


def upgrade() -> None:
    # ─── roles ───────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("grants_all", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
    )
    op.create_index("ix_roles_id", "roles", ["id"])
    # System roles have tenant_id NULL, and Postgres treats NULLs as distinct,
    # so the composite unique constraint above does not cover them.
    op.create_index(
        "uq_role_system_code", "roles", ["code"], unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )

    # ─── permissions ─────────────────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(96), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requires_step_up", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("role_id", sa.Integer(),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission_id", sa.Integer(),
                  sa.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role", "role_permissions", ["role_id"])

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Integer(),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("granted_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )
    op.create_index("ix_user_roles_user", "user_roles", ["user_id"])

    # ─── MFA ─────────────────────────────────────────────────────────────────
    op.create_table(
        "mfa_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="totp"),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_counter", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mfa_credentials_user", "mfa_credentials", ["user_id"])

    op.create_table(
        "step_up_assertions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("session_jti", sa.String(64), nullable=True),
        sa.Column("purpose", sa.String(96), nullable=False),
        sa.Column("mfa_method", sa.String(32), nullable=False, server_default="totp"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_step_up_token_hash", "step_up_assertions", ["token_hash"],
                    unique=True)
    op.create_index("ix_step_up_session", "step_up_assertions", ["session_jti"])
    op.create_index("ix_step_up_user_purpose", "step_up_assertions",
                    ["user_id", "purpose"])

    # ─── audit log ───────────────────────────────────────────────────────────
    # No foreign key on actor_id, deliberately. Audit entries outlive the users
    # they describe; a FK would either block deletion or cascade away the
    # evidence. The id is recorded as a plain value.
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("seq", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(64), nullable=True),
        sa.Column("action", sa.String(96), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("session_jti", sa.String(64), nullable=True),
        sa.Column("mfa_method", sa.String(32), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.CheckConstraint("result IN ('success','denied','error')",
                           name="ck_audit_result"),
    )
    op.create_index("ix_audit_seq", "audit_log", ["seq"], unique=True)
    op.create_index("ix_audit_action", "audit_log", ["action"])
    op.create_index("ix_audit_tenant_time", "audit_log", ["tenant_id", "occurred_at"])
    op.create_index("ix_audit_actor_time", "audit_log", ["actor_id", "occurred_at"])
    op.create_index("ix_audit_target", "audit_log",
                    ["target_type", "target_id", "occurred_at"])

    _seed()
    _enforce_append_only()


def _seed() -> None:
    conn = op.get_bind()

    for code, description, step_up in PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (code, description, requires_step_up) "
                "VALUES (:c, :d, :s) ON CONFLICT (code) DO NOTHING"
            ),
            {"c": code, "d": description, "s": step_up},
        )

    for code, name, description, grants_all, perms in SYSTEM_ROLES:
        conn.execute(
            sa.text(
                "INSERT INTO roles (tenant_id, code, name, description, is_system, "
                "grants_all) VALUES (NULL, :c, :n, :d, true, :g) "
                "ON CONFLICT DO NOTHING"
            ),
            {"c": code, "n": name, "d": description, "g": grants_all},
        )
        if not perms:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r, permissions p "
                "WHERE r.code = :c AND r.tenant_id IS NULL AND p.code = ANY(:perms) "
                "ON CONFLICT DO NOTHING"
            ),
            {"c": code, "perms": list(perms)},
        )


def _enforce_append_only() -> None:
    """
    Revoke UPDATE and DELETE on audit_log from the application role.

    This is the control. Everything else about the audit log — the hash chain,
    the careful writer — is evidence-gathering; this is what makes rewriting
    history require a different set of credentials from running the app.

    Best-effort by design: the role name differs per environment, and a fresh
    database with no separate app role must still migrate. A failure prints a
    loud warning rather than aborting, because an un-migrated database is worse
    than one where this has to be applied by hand.
    """
    conn = op.get_bind()
    candidates = ("app_user", "gridsphere_app", "biometric")

    applied = []
    for role in candidates:
        exists = conn.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
        ).first()
        if not exists:
            continue
        try:
            conn.execute(
                sa.text(f'REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM "{role}"')
            )
            applied.append(role)
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"  [audit] could not revoke on {role}: {exc}")

    if applied:
        print(f"  [audit] append-only enforced for: {', '.join(applied)}")
    else:
        print(
            "  [audit] WARNING: no application role found, so audit_log is NOT "
            "append-only at the database level.\n"
            "  [audit] The hash chain still detects tampering, but nothing "
            "PREVENTS it.\n"
            "  [audit] Create a limited role and run:\n"
            "  [audit]   REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM <role>;"
        )


def downgrade() -> None:
    # audit_log is dropped last: if a later step fails, the evidence outlives
    # the partial rollback.
    op.drop_table("step_up_assertions")
    op.drop_table("mfa_credentials")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("audit_log")
