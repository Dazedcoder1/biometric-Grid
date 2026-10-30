"""HR access.

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6

  users.is_hr      an employee or Org Admin who also runs payroll. Their own
                   role is unchanged — HR is added on top of it, so they keep
                   their attendance, leave and My Pay screens.
  role "hr"        system role with payroll.view, payroll.manage,
                   payroll.approve and reimbursement.approve. Added to a
                   person's permissions while is_hr is set
                   (deps_security.load_permissions).

Who can grant it: anyone with role.assign in the organisation — Tenant
Admins, and Super Admins through grants_all.
"""

from alembic import op
import sqlalchemy as sa

revision = "g2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


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

HR_PERMISSIONS = ("payroll.view", "payroll.manage", "payroll.approve", "reimbursement.approve")


def upgrade() -> None:
    _ensure_column("users", sa.Column("is_hr", sa.Boolean(), nullable=False, server_default="false"),
                   fill_sql="false")

    conn = op.get_bind()
    exists = conn.execute(sa.text("SELECT id FROM roles WHERE code = 'hr' AND tenant_id IS NULL")).first()
    if not exists:
        conn.execute(sa.text(
            "INSERT INTO roles (tenant_id, code, name, description, is_system, grants_all) "
            "VALUES (NULL, 'hr', 'HR', "
            "'Runs payroll and decides expense claims for the organisation.', true, false)"
        ))
    for perm in HR_PERMISSIONS:
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id FROM roles r, permissions p
                 WHERE r.code = 'hr' AND r.tenant_id IS NULL AND p.code = :p
                ON CONFLICT DO NOTHING
                """
            ),
            {"p": perm},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM role_permissions WHERE role_id IN "
        "(SELECT id FROM roles WHERE code = 'hr' AND tenant_id IS NULL)"
    ))
    conn.execute(sa.text("DELETE FROM user_roles WHERE role_id IN "
                         "(SELECT id FROM roles WHERE code = 'hr' AND tenant_id IS NULL)"))
    conn.execute(sa.text("DELETE FROM roles WHERE code = 'hr' AND tenant_id IS NULL"))
    op.drop_column("users", "is_hr")
