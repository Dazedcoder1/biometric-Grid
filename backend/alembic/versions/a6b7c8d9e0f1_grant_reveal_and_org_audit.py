"""Grant tenant_admin credential.reveal, and org_admin audit.view.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0

Two grants the catalogue in app/core/permissions.py now declares. They need a
migration because role_permissions is read from the database at request time —
editing the catalogue alone changes what the source says a role can do without
changing what it can actually do, and e4f5a6b7c8d9 seeded these rows once and
will not run again.

Why each:

  tenant_admin -> credential.reveal
      Withheld while the only way to be a Tenant Admin was a long-lived API
      key: a key carries a tenant and not a person, so the audit log could not
      name who held it, and a key cannot enrol a second factor. Both premises
      are gone. Tenant Admins now sign in with a password, appear in the audit
      log by name, and enrol an authenticator like anyone else. The key path
      remains barred by mechanism rather than by this grant — reveal requires a
      fresh step-up assertion bound to a user and a session, and an API-key
      caller can produce neither.

  org_admin -> audit.view
      The audit endpoint already scopes to the caller's tenant, so this shows
      an Org Admin their own organisation and nothing else. They could already
      reveal secrets and grant shares — the actions the log records — but not
      read the record of them, and the sidebar linked them to a page where
      every request returned 403.

Deliberately NOT granted: audit.verify. The verification pass walks the whole
chain across every tenant, so its result discloses the volume and head hash of
other organisations' activity. It stays with the platform operator until the
pass can be scoped per tenant.

Reversible: downgrade removes exactly these two rows and nothing else.
"""

from alembic import op
import sqlalchemy as sa

revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None

#: (role code, permission code)
GRANTS = [
    ("tenant_admin", "credential.reveal"),
    ("org_admin", "audit.view"),
]

# Only the seeded, tenant-wide system roles. A tenant that created a custom
# role happening to share one of these codes must not be altered by a platform
# migration — hence `tenant_id IS NULL` on every statement below.
_INSERT = sa.text(
    """
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT r.id, p.id
      FROM roles r, permissions p
     WHERE r.code = :role AND r.tenant_id IS NULL
       AND p.code = :perm
    ON CONFLICT DO NOTHING
    """
)

_DELETE = sa.text(
    """
    DELETE FROM role_permissions
     WHERE role_id = (SELECT id FROM roles WHERE code = :role AND tenant_id IS NULL)
       AND permission_id = (SELECT id FROM permissions WHERE code = :perm)
    """
)


def upgrade() -> None:
    conn = op.get_bind()
    for role, perm in GRANTS:
        # Fail loudly if the permission row is missing rather than inserting
        # nothing and reporting success: a silent no-op here looks exactly like
        # a working migration and leaves the role still unable to act.
        exists = conn.execute(
            sa.text("SELECT 1 FROM permissions WHERE code = :perm"), {"perm": perm}
        ).first()
        if not exists:
            raise RuntimeError(
                f"Permission {perm!r} is not in the permissions table. "
                "Migration e4f5a6b7c8d9 seeds the catalogue — run it first."
            )
        conn.execute(_INSERT, {"role": role, "perm": perm})


def downgrade() -> None:
    conn = op.get_bind()
    for role, perm in GRANTS:
        conn.execute(_DELETE, {"role": role, "perm": perm})
