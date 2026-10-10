"""Systems belong to departments.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3

Until now the dependency map was organisation-wide: every role, employees
included, saw every system and every credential name in the company. Systems
now carry a department, and people see their own department's systems plus the
shared ones. A Tenant Admin sees everything.

  systems.department_id   NULL = shared, visible to the whole organisation.

  Backfill. A system is assigned to a department when every live credential
  linked to it is owned by someone in that one department. Anything linked
  from several departments, owned by someone with no department, or not
  linked at all stays shared — nothing becomes less visible than it is today
  unless the data says clearly whose it is. The Tenant Admin can correct any
  of it from the map.

  Uniqueness moves from (tenant, name, environment) to (tenant, department,
  name, environment), so Production and Testing can each have an "api"
  without colliding. Every existing row is already unique under the old rule,
  so it is unique under the new one too.

  permission system.manage
      Move a system between departments, or make it shared. Granted to
      tenant_admin (any department) and org_admin (their own department and
      shared only — enforced in dependency_service.move_system).

Downgrade restores the old uniqueness. It will FAIL if two departments have
since created systems with the same name and environment — that is the data
telling you the old rule no longer fits, and is better than silently merging.
"""

from alembic import op
import sqlalchemy as sa

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None

PERMISSION = ("system.manage", "Move a system between departments, or make it shared")
GRANTS = [("tenant_admin", "system.manage"), ("org_admin", "system.manage")]

_BACKFILL = sa.text(
    """
    UPDATE systems s
       SET department_id = owners.dept_id
      FROM (
            SELECT d.system_id,
                   MIN(u.dept_id) AS dept_id
              FROM credential_dependencies d
              JOIN credentials c ON c.id = d.credential_id AND c.deleted_at IS NULL
              JOIN users u       ON u.id = c.owner_id
             GROUP BY d.system_id
            -- every owner has a department, and it is the same one
            HAVING BOOL_AND(u.dept_id IS NOT NULL)
               AND COUNT(DISTINCT u.dept_id) = 1
           ) owners
      JOIN departments dep ON dep.department_id = owners.dept_id
     WHERE s.id = owners.system_id
       AND dep.tenant_id = s.tenant_id
    """
)


def upgrade() -> None:
    op.add_column("systems", sa.Column("department_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_systems_department", "systems", "departments",
        ["department_id"], ["department_id"], ondelete="SET NULL",
    )
    op.create_index("ix_systems_department_id", "systems", ["department_id"])

    conn = op.get_bind()
    conn.execute(_BACKFILL)

    op.drop_constraint("uq_system_tenant_name_env", "systems", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX uq_system_tenant_dept_name_env "
        "ON systems (tenant_id, COALESCE(department_id, 0), name, environment)"
    )

    code, description = PERMISSION
    conn.execute(
        sa.text(
            "INSERT INTO permissions (code, description, requires_step_up) "
            "VALUES (:c, :d, false) ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description"
        ),
        {"c": code, "d": description},
    )
    for role, perm in GRANTS:
        exists = conn.execute(
            sa.text("SELECT 1 FROM roles WHERE code = :r AND tenant_id IS NULL"), {"r": role}
        ).first()
        if not exists:
            raise RuntimeError(
                f"System role {role!r} is not in the roles table. "
                "Migration e4f5a6b7c8d9 seeds the roles — run it first."
            )
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id FROM roles r, permissions p
                 WHERE r.code = :r AND r.tenant_id IS NULL AND p.code = :p
                ON CONFLICT DO NOTHING
                """
            ),
            {"r": role, "p": perm},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for role, perm in GRANTS:
        conn.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                 WHERE role_id = (SELECT id FROM roles WHERE code = :r AND tenant_id IS NULL)
                   AND permission_id = (SELECT id FROM permissions WHERE code = :p)
                """
            ),
            {"r": role, "p": perm},
        )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": PERMISSION[0]})

    op.execute("DROP INDEX IF EXISTS uq_system_tenant_dept_name_env")
    op.create_unique_constraint(
        "uq_system_tenant_name_env", "systems", ["tenant_id", "name", "environment"]
    )
    op.drop_index("ix_systems_department_id", table_name="systems")
    op.drop_constraint("fk_systems_department", "systems", type_="foreignkey")
    op.drop_column("systems", "department_id")
