"""
Credential vault schema — vaults, racks, credentials, versions, payloads,
shares, teams, ownership history, rotation policies and dependencies.

Design rationale is in docs/DATA-MODEL.md. The decisions taken here, which
that document left open:

1. `teams` is SEPARATE from the existing `departments`. Departments already
   carry attendance semantics — `users.dept_id` scopes org-admin authority and
   leave approval. Reusing them for sharing would mean "share with Engineering"
   silently implies attendance-management scope. Sharing groups rarely match
   the org chart anyway.

2. Notifications EXTEND the existing table rather than a second system. It
   already has event_type, entity_type, entity_id, title, message and read
   state; only `severity` is missing.

3. Retention (decision 8, 90 days) runs as a scheduled script, not the
   in-process loop. Destroying payloads is irreversible and belongs in
   something deliberate and auditable.

4. Credentials soft-delete via `deleted_at`. Audit history referencing a
   deleted credential must stay meaningful.

One deviation from DATA-MODEL.md: dependencies point at a `systems` table
rather than holding a free-text system name. Phase 9 requires systems to be
reusable entities ("one system can depend on many credentials"), and migrating
strings into entities later would mean reconciling every typo.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.models.domain import Base

# ─────────────────────────────────────────────────────────────────────────────
# Vaults and racks
# ─────────────────────────────────────────────────────────────────────────────


class Vault(Base):
    """
    One personal and one shared vault per user, created on first login.

    The SHARED vault stores nothing. Its contents are derived from active
    shares — storing copies would create a second source of truth for access,
    and the copy would eventually disagree with the grant. In a credential
    system that means someone keeps visible access after revocation.
    """

    __tablename__ = "vaults"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    kind = Column(String(16), nullable=False)  # personal | shared
    name = Column(String(128), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("owner_user_id", "kind", name="uq_vault_owner_kind"),
        CheckConstraint("kind IN ('personal','shared')", name="ck_vault_kind"),
        Index("ix_vaults_tenant_owner", "tenant_id", "owner_user_id"),
    )


class Rack(Base):
    """A folder inside a vault — GitHub, Google, Teams, Other."""

    __tablename__ = "racks"

    id = Column(Integer, primary_key=True)
    vault_id = Column(Integer, ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(128), nullable=False)
    icon = Column(String(64), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("vault_id", "name", name="uq_rack_vault_name"),
        Index("ix_racks_vault", "vault_id", "sort_order"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Credentials: metadata, versions, ciphertext
# ─────────────────────────────────────────────────────────────────────────────


class Credential(Base):
    """
    Searchable metadata. The secret lives in EncryptedPayload, two tables away.

    Splitting them means listing a rack reads only this table — ciphertext is
    loaded on reveal and at no other time, so no ordinary query can page secret
    bytes into memory or a log.

    `notes` is deliberately absent. Notes are where people write recovery
    codes, so they belong in the encrypted payload, not in a cleartext column.
    """

    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    rack_id = Column(Integer, ForeignKey("racks.id", ondelete="RESTRICT"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    name = Column(String(255), nullable=False)
    kind = Column(String(32), nullable=False, default="password")
    username = Column(String(255), nullable=True)
    url = Column(Text, nullable=True)
    has_2fa = Column(Boolean, nullable=False, default=False)

    # Denormalised pointer to the live version. The alternative — ordering
    # versions descending on every read — costs a sort per credential per view.
    # Both writes happen in one service method; never set this by hand.
    current_version_id = Column(Integer, nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

    # Soft delete. RESTRICT on rack_id and owner_id above is intentional: a
    # rack or user with live credentials must be dealt with explicitly rather
    # than cascading secrets away.
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "kind IN ('password','api_key','token','ssh_key','certificate','other')",
            name="ck_credential_kind",
        ),
        Index("ix_credentials_tenant_rack", "tenant_id", "rack_id"),
        Index("ix_credentials_owner", "owner_id"),
        Index(
            "ix_credentials_rack_live", "rack_id", "name",
            postgresql_where=Column("deleted_at").is_(None),
        ),
    )


class CredentialVersion(Base):
    """
    One row per version. Rotation appends; it never updates in place.

    `destroyed_at` records that the payload was deleted under the retention
    policy while keeping the fact of the version — so the audit trail can still
    say "version 3 existed, Alice created it, destroyed on this date" with
    nothing decryptable left.
    """

    __tablename__ = "credential_versions"

    id = Column(Integer, primary_key=True)
    credential_id = Column(
        Integer, ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False
    )
    version = Column(Integer, nullable=False)

    payload_id = Column(
        Integer, ForeignKey("encrypted_payloads.id", ondelete="SET NULL"), nullable=True
    )

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    destroyed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("credential_id", "version", name="uq_version_credential_number"),
        Index("ix_versions_credential_desc", "credential_id", "version"),
    )


class EncryptedPayload(Base):
    """
    Ciphertext and the wrapped key that opens it. Never queried by content.

    One DEK per row, used for exactly one encryption. That is what removes
    AES-GCM's nonce-reuse risk structurally rather than by discipline — there
    is no second encryption under the key to collide with. SECURITY.md §3.2.

    `aad_context` records what was bound into the AEAD tag (tenant, credential,
    version), so a verifier can reconstruct it without guessing.
    """

    __tablename__ = "encrypted_payloads"

    id = Column(Integer, primary_key=True)

    ciphertext = Column(LargeBinary, nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    wrapped_dek = Column(LargeBinary, nullable=False)

    kek_id = Column(String(255), nullable=False)
    alg = Column(String(64), nullable=False, default="AES-256-GCM")
    aad_context = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexed only for the re-encryption pass, which walks payloads still under
    # an old KEK. Everything else reaches this table by id from a version row.
    __table_args__ = (Index("ix_payloads_kek", "kek_id"),)


# ─────────────────────────────────────────────────────────────────────────────
# Teams
# ─────────────────────────────────────────────────────────────────────────────


class Team(Base):
    """Sharing group. Separate from `departments` — see the module docstring."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_team_tenant_name"),
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    added_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        Index("ix_team_members_user", "user_id"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sharing
# ─────────────────────────────────────────────────────────────────────────────


class Share(Base):
    """
    A grant, and a node in the sharing tree.

    `parent_share_id` is the source of truth; `path` is a materialised string
    (`/12/48/93/`) written once at insert. A materialised path is normally a
    liability because moving a node rewrites every descendant — but a share
    never moves. Revoking changes `status`, not the tree. So the path costs
    nothing to maintain and turns the approved cascade revoke into one indexed
    statement:

        UPDATE shares SET status='revoked'
         WHERE path LIKE '/12/48/%' AND status='active';

    Rows are never deleted. A revoked share is evidence that access existed and
    was withdrawn; deleting it erases what an investigation needs.
    """

    __tablename__ = "shares"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    credential_id = Column(
        Integer, ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False
    )

    parent_share_id = Column(
        Integer, ForeignKey("shares.id", ondelete="RESTRICT"), nullable=True
    )
    path = Column(Text, nullable=False)

    grantor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    grantee_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    grantee_team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)

    permission = Column(String(16), nullable=False)

    starts_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(String(16), nullable=False, default="active")

    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Exactly one grantee. Without this a row could target both a user and
        # a team, or neither, and every consumer would need to handle it.
        CheckConstraint(
            "(grantee_user_id IS NOT NULL)::int + (grantee_team_id IS NOT NULL)::int = 1",
            name="ck_share_single_grantee",
        ),
        CheckConstraint(
            "permission IN ('view','reveal','edit','reshare','manage')",
            name="ck_share_permission",
        ),
        CheckConstraint(
            "status IN ('pending','active','expired','revoked')",
            name="ck_share_status",
        ),
        Index("ix_shares_credential", "credential_id"),
        Index("ix_shares_tenant", "tenant_id"),
        # Partial indexes: most shares end revoked or expired, but "what can I
        # see" only asks about active ones. Indexing all of them would grow
        # forever while the useful portion stays small.
        Index(
            "ix_shares_grantee_active", "grantee_user_id",
            postgresql_where=Column("status") == "active",
        ),
        Index(
            "ix_shares_team_active", "grantee_team_id",
            postgresql_where=Column("status") == "active",
        ),
        Index(
            "ix_shares_expiring", "expires_at",
            postgresql_where=Column("status") == "active",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# History, policy, dependencies
# ─────────────────────────────────────────────────────────────────────────────


class OwnershipHistory(Base):
    """
    Append-only ledger of transfers. `credentials.owner_id` is the current
    pointer; this is the record. The pointer is overwritten — it is a pointer —
    but no history is lost, because the ledger row is written in the same
    transaction.
    """

    __tablename__ = "ownership_history"

    id = Column(Integer, primary_key=True)
    credential_id = Column(
        Integer, ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False
    )

    from_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_ownership_credential_time", "credential_id", "changed_at"),
    )


class RotationPolicy(Base):
    """
    How often a secret should change. Attaches to one credential or a whole
    rack; exactly one, so resolution is unambiguous.
    """

    __tablename__ = "rotation_policies"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    credential_id = Column(
        Integer, ForeignKey("credentials.id", ondelete="CASCADE"), nullable=True
    )
    rack_id = Column(Integer, ForeignKey("racks.id", ondelete="CASCADE"), nullable=True)

    interval_days = Column(Integer, nullable=False, default=90)
    warn_days_before = Column(Integer, nullable=False, default=14)
    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "(credential_id IS NOT NULL)::int + (rack_id IS NOT NULL)::int = 1",
            name="ck_rotation_single_target",
        ),
        CheckConstraint("interval_days > 0", name="ck_rotation_interval_positive"),
        Index("ix_rotation_credential", "credential_id"),
        Index("ix_rotation_rack", "rack_id"),
    )


class System(Base):
    """
    A thing that consumes credentials — Docker, a Postgres instance, a GitHub
    Actions workflow. Reusable, so one system can depend on many credentials
    and the org-wide dependency graph in Phase 9 has real nodes to draw.
    """

    __tablename__ = "systems"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    kind = Column(String(64), nullable=True)
    environment = Column(String(32), nullable=True)  # production | staging | dev
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "environment", name="uq_system_tenant_name_env"),
    )


class CredentialDependency(Base):
    """
    "What breaks if this is rotated." Read before any rotation or revocation.
    """

    __tablename__ = "credential_dependencies"

    id = Column(Integer, primary_key=True)
    credential_id = Column(
        Integer, ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False
    )
    system_id = Column(Integer, ForeignKey("systems.id", ondelete="CASCADE"), nullable=False)

    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("credential_id", "system_id", name="uq_dependency_pair"),
        # Both directions are asked: "what breaks if I rotate this credential"
        # and "which credentials does this system need".
        Index("ix_dependency_credential", "credential_id"),
        Index("ix_dependency_system", "system_id"),
    )
