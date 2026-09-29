"""Phase 3: vaults, racks, credentials, versions, payloads, shares, teams

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-29

Twelve tables plus two column additions. Rationale in docs/DATA-MODEL.md and
app/models/credentials.py.

Order matters: vaults before racks before credentials before versions, because
each depends on the last. encrypted_payloads comes before credential_versions
since versions reference payloads.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── users: employment status ────────────────────────────────────────────
    # Offboarding is where credential systems fail. 'leaving' triggers a
    # handover checklist; 'deactivated' revokes shares and flags owned
    # credentials for reassignment.
    op.add_column(
        "users",
        sa.Column("employment_status", sa.String(16), nullable=False,
                  server_default="active"),
    )
    op.add_column(
        "users",
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_users_employment_status",
        "users",
        "employment_status IN ('active','leaving','deactivated')",
    )
    op.create_index("ix_users_employment_status", "users", ["employment_status"])

    # ─── notifications: severity ─────────────────────────────────────────────
    # Extending the existing table rather than building a second notification
    # system. It already carries event_type, entity refs, title, body and read
    # state; only severity was missing.
    op.add_column(
        "notifications",
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
    )

    # ─── vaults ──────────────────────────────────────────────────────────────
    op.create_table(
        "vaults",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("owner_user_id", "kind", name="uq_vault_owner_kind"),
        sa.CheckConstraint("kind IN ('personal','shared')", name="ck_vault_kind"),
    )
    op.create_index("ix_vaults_tenant_owner", "vaults", ["tenant_id", "owner_user_id"])

    # ─── racks ───────────────────────────────────────────────────────────────
    op.create_table(
        "racks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vault_id", sa.Integer(),
                  sa.ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("icon", sa.String(64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("vault_id", "name", name="uq_rack_vault_name"),
    )
    op.create_index("ix_racks_vault", "racks", ["vault_id", "sort_order"])

    # ─── encrypted payloads ──────────────────────────────────────────────────
    # Before credential_versions, which references it.
    op.create_table(
        "encrypted_payloads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("kek_id", sa.String(255), nullable=False),
        sa.Column("alg", sa.String(64), nullable=False, server_default="AES-256-GCM"),
        sa.Column("aad_context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_payloads_kek", "encrypted_payloads", ["kek_id"])

    # ─── credentials ─────────────────────────────────────────────────────────
    op.create_table(
        "credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rack_id", sa.Integer(),
                  sa.ForeignKey("racks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="password"),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("has_2fa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "kind IN ('password','api_key','token','ssh_key','certificate','other')",
            name="ck_credential_kind",
        ),
    )
    op.create_index("ix_credentials_tenant_rack", "credentials", ["tenant_id", "rack_id"])
    op.create_index("ix_credentials_owner", "credentials", ["owner_id"])
    # Partial: every normal read excludes soft-deleted rows.
    op.create_index(
        "ix_credentials_rack_live", "credentials", ["rack_id", "name"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ─── credential versions ─────────────────────────────────────────────────
    op.create_table(
        "credential_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credential_id", sa.Integer(),
                  sa.ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload_id", sa.Integer(),
                  sa.ForeignKey("encrypted_payloads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("credential_id", "version", name="uq_version_credential_number"),
    )
    op.create_index(
        "ix_versions_credential_desc", "credential_versions",
        ["credential_id", sa.text("version DESC")],
    )

    # current_version_id could not be a FK at creation time — credentials is
    # created before credential_versions exists. Added now that both do.
    op.create_foreign_key(
        "fk_credentials_current_version", "credentials", "credential_versions",
        ["current_version_id"], ["id"], ondelete="SET NULL",
    )

    # ─── teams ───────────────────────────────────────────────────────────────
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_team_tenant_name"),
    )

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("added_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )
    op.create_index("ix_team_members_user", "team_members", ["user_id"])

    # ─── shares ──────────────────────────────────────────────────────────────
    op.create_table(
        "shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.Integer(),
                  sa.ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_share_id", sa.Integer(),
                  sa.ForeignKey("shares.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("grantor_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grantee_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("grantee_team_id", sa.Integer(),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=True),
        sa.Column("permission", sa.String(16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "(grantee_user_id IS NOT NULL)::int + (grantee_team_id IS NOT NULL)::int = 1",
            name="ck_share_single_grantee",
        ),
        sa.CheckConstraint(
            "permission IN ('view','reveal','edit','reshare','manage')",
            name="ck_share_permission",
        ),
        sa.CheckConstraint(
            "status IN ('pending','active','expired','revoked')",
            name="ck_share_status",
        ),
    )
    op.create_index("ix_shares_credential", "shares", ["credential_id"])
    op.create_index("ix_shares_tenant", "shares", ["tenant_id"])

    # text_pattern_ops, NOT the default operator class. The default supports
    # equality and ordering under the database collation but not LIKE
    # 'prefix%' unless the database is in the C locale — Neon is not. Without
    # this the cascade-revoke query silently becomes a sequential scan. It
    # still returns correct answers, which is why the mistake survives review.
    op.execute(
        "CREATE INDEX ix_shares_path ON shares (path text_pattern_ops)"
    )

    # Partial indexes on live rows only — most shares end revoked or expired,
    # but "what can I see" only ever asks about active ones.
    op.create_index(
        "ix_shares_grantee_active", "shares", ["grantee_user_id"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_shares_team_active", "shares", ["grantee_team_id"],
        postgresql_where=sa.text("status = 'active' AND grantee_team_id IS NOT NULL"),
    )
    op.create_index(
        "ix_shares_expiring", "shares", ["expires_at"],
        postgresql_where=sa.text("status = 'active' AND expires_at IS NOT NULL"),
    )

    # ─── ownership history ───────────────────────────────────────────────────
    op.create_table(
        "ownership_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credential_id", sa.Integer(),
                  sa.ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_ownership_credential_time", "ownership_history",
        ["credential_id", sa.text("changed_at DESC")],
    )

    # ─── rotation policies ───────────────────────────────────────────────────
    op.create_table(
        "rotation_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credential_id", sa.Integer(),
                  sa.ForeignKey("credentials.id", ondelete="CASCADE"), nullable=True),
        sa.Column("rack_id", sa.Integer(),
                  sa.ForeignKey("racks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("warn_days_before", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "(credential_id IS NOT NULL)::int + (rack_id IS NOT NULL)::int = 1",
            name="ck_rotation_single_target",
        ),
        sa.CheckConstraint("interval_days > 0", name="ck_rotation_interval_positive"),
    )
    op.create_index("ix_rotation_credential", "rotation_policies", ["credential_id"])
    op.create_index("ix_rotation_rack", "rotation_policies", ["rack_id"])

    # ─── systems and dependencies ────────────────────────────────────────────
    op.create_table(
        "systems",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(64), nullable=True),
        sa.Column("environment", sa.String(32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", "environment",
                            name="uq_system_tenant_name_env"),
    )

    op.create_table(
        "credential_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credential_id", sa.Integer(),
                  sa.ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("system_id", sa.Integer(),
                  sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("credential_id", "system_id", name="uq_dependency_pair"),
    )
    op.create_index("ix_dependency_credential", "credential_dependencies", ["credential_id"])
    op.create_index("ix_dependency_system", "credential_dependencies", ["system_id"])


def downgrade() -> None:
    # Reverse creation order. The self-referencing FK on shares and the
    # circular one between credentials and credential_versions mean the FK has
    # to go before the tables.
    op.drop_constraint("fk_credentials_current_version", "credentials", type_="foreignkey")

    op.drop_table("credential_dependencies")
    op.drop_table("systems")
    op.drop_table("rotation_policies")
    op.drop_table("ownership_history")
    op.drop_table("shares")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("credential_versions")
    op.drop_table("credentials")
    op.drop_table("encrypted_payloads")
    op.drop_table("racks")
    op.drop_table("vaults")

    op.drop_column("notifications", "severity")
    op.drop_index("ix_users_employment_status", table_name="users")
    op.drop_constraint("ck_users_employment_status", "users", type_="check")
    op.drop_column("users", "status_changed_at")
    op.drop_column("users", "employment_status")
