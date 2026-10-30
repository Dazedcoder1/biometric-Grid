"""Vault oversight and admin password reset.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2

Three changes, all additive:

  users.must_change_password
      Set when an administrator issues a temporary password. Until the person
      picks their own, every authenticated route except changing it refuses
      them (app/api/dependencies.get_current_user). Defaults to false, so no
      existing account is affected.

  permission credential.oversee   (requires step-up)
      See and reveal credentials in the vaults of people you administer,
      without a share. Granted to tenant_admin and org_admin. WHOSE vaults is
      decided in app/services/oversight_service.py: a Tenant Admin reaches
      Org Admins and Employees in their organisation; an Org Admin reaches
      Employees in their own department. Never peers, never upward.

  permission user.password_reset
      Issue a temporary sign-in password to someone you administer. Same
      grantees and the same scope rule. Replaces /api/auth/set-password, which
      let any Org Admin set any user's password in any organisation —
      including a Super Admin's.

They need a migration, not just a catalogue edit, because role_permissions is
read from the database on every request. Changing app/core/permissions.py
alone would change what the source says a role can do without changing what
it actually can.

Reversible: downgrade removes exactly these grants, permissions and column.
"""

from alembic import op
import sqlalchemy as sa

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None

#: (code, description, requires_step_up)
PERMISSIONS = [
    (
        "credential.oversee",
        "See and reveal credentials in the vaults of people you administer",
        True,
    ),
    (
        "user.password_reset",
        "Issue a temporary sign-in password to someone you administer",
        False,
    ),
]

#: (role code, permission code)
GRANTS = [
    ("tenant_admin", "credential.oversee"),
    ("tenant_admin", "user.password_reset"),
    ("org_admin", "credential.oversee"),
    ("org_admin", "user.password_reset"),
]

_INSERT_PERMISSION = sa.text(
    """
    INSERT INTO permissions (code, description, requires_step_up)
    VALUES (:code, :description, :step_up)
    ON CONFLICT (code) DO UPDATE
       SET description = EXCLUDED.description,
           requires_step_up = EXCLUDED.requires_step_up
    """
)

# Only the seeded, tenant-wide system roles. A tenant's custom role that
# happens to share one of these codes must not be altered by a platform
# migration — hence `tenant_id IS NULL`.
_INSERT_GRANT = sa.text(
    """
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT r.id, p.id
      FROM roles r, permissions p
     WHERE r.code = :role AND r.tenant_id IS NULL
       AND p.code = :perm
    ON CONFLICT DO NOTHING
    """
)

_DELETE_GRANT = sa.text(
    """
    DELETE FROM role_permissions
     WHERE role_id = (SELECT id FROM roles WHERE code = :role AND tenant_id IS NULL)
       AND permission_id = (SELECT id FROM permissions WHERE code = :perm)
    """
)




def _ensure_column(table: str, column: sa.Column, fill_sql: str | None = None) -> None:
    """Add the column, or — if it already exists — bring it in line.

    b1c2d3e4f5a6 builds tables from the *current* models, so on a fresh
    database this column can already be there (added nullable). Rather than
    fail with DuplicateColumn, backfill and apply this migration's definition.
    """
    bind = op.get_bind()
    present = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    if column.name not in present:
        op.add_column(table, column)
        return
    if fill_sql is not None:
        bind.execute(sa.text(
            f"UPDATE {table} SET {column.name} = {fill_sql} WHERE {column.name} IS NULL"
        ))
    op.alter_column(
        table, column.name,
        existing_type=column.type,
        nullable=column.nullable,
        server_default=column.server_default.arg if column.server_default is not None else None,
    )
def upgrade() -> None:
    _ensure_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        fill_sql="false",
    )

    conn = op.get_bind()
    for code, description, step_up in PERMISSIONS:
        conn.execute(
            _INSERT_PERMISSION,
            {"code": code, "description": description, "step_up": step_up},
        )

    for role, perm in GRANTS:
        # Fail loudly if the role is missing rather than inserting nothing and
        # reporting success — a silent no-op here looks exactly like a working
        # migration and leaves the role unable to use the feature.
        exists = conn.execute(
            sa.text("SELECT 1 FROM roles WHERE code = :role AND tenant_id IS NULL"),
            {"role": role},
        ).first()
        if not exists:
            raise RuntimeError(
                f"System role {role!r} is not in the roles table. "
                "Migration e4f5a6b7c8d9 seeds the roles — run it first."
            )
        conn.execute(_INSERT_GRANT, {"role": role, "perm": perm})


def downgrade() -> None:
    conn = op.get_bind()
    for role, perm in GRANTS:
        conn.execute(_DELETE_GRANT, {"role": role, "perm": perm})
    for code, _description, _step_up in PERMISSIONS:
        conn.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})
    op.drop_column("users", "must_change_password")
