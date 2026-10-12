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

HR_PERMISSIONS = ("payroll.view", "payroll.manage", "payroll.approve", "reimbursement.approve")


def upgrade() -> None:
    op.add_column("users", sa.Column("is_hr", sa.Boolean(), nullable=False, server_default="false"))

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
