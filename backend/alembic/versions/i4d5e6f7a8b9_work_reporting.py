"""Work reporting and targets.

Revision ID: i4d5e6f7a8b9
Revises: h3c4d5e6f7a8

  targets (+ milestones, updates)   goals with a start and end, progress and
                                    milestones, shown on a Gantt timeline;
                                    owned by a person or a department
  work_assignments                  the focus an admin sets for a person, for
                                    a day or a week
  daily_reports (+ lines)           one day-end report per person per day,
                                    with what they did and the hours

Permissions
  report.view     read the daily reports of people you oversee
  report.manage   assign a focus, and review reports
  target.view     read the targets of people you oversee
  target.manage   create and assign targets and milestones

Granted to tenant_admin, org_admin and hr. Employees write their own reports
and keep their own targets' progress through ownership, so need no grant.
Who an admin can see is scoped by the oversight hierarchy, enforced in the
routes.
"""

from alembic import op
import sqlalchemy as sa

revision = "i4d5e6f7a8b9"
down_revision = "h3c4d5e6f7a8"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("report.view", "Read the day-end reports of people you oversee"),
    ("report.manage", "Assign a daily or weekly focus, and review reports"),
    ("target.view", "Read the targets of people you oversee"),
    ("target.manage", "Create and assign targets and milestones"),
]
GRANTS = [(role, code) for role in ("tenant_admin", "org_admin", "hr") for code, _ in PERMISSIONS]


def _ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now())


def _fk_user(name, ondelete="SET NULL", nullable=True):
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        _fk_user("user_id", ondelete="CASCADE"),
        sa.Column("dept_id", sa.Integer(), sa.ForeignKey("departments.department_id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        _fk_user("created_by"), _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_targets_tenant_id", "targets", ["tenant_id"])
    op.create_index("ix_targets_user_id", "targets", ["user_id"])
    op.create_index("ix_target_tenant_dates", "targets", ["tenant_id", "start_date", "end_date"])

    op.create_table(
        "target_milestones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_target_milestones_target_id", "target_milestones", ["target_id"])

    op.create_table(
        "target_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("targets.id", ondelete="CASCADE"), nullable=False),
        _fk_user("user_id"),
        sa.Column("progress", sa.Integer()),
        sa.Column("note", sa.String(1000)),
        _ts("created_at"),
    )
    op.create_index("ix_target_updates_target_id", "target_updates", ["target_id"])

    op.create_table(
        "work_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(8), nullable=False, server_default="day"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("details", sa.Text()),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("targets.id", ondelete="SET NULL")),
        _fk_user("assigned_by"), _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_work_assignments_tenant_id", "work_assignments", ["tenant_id"])
    op.create_index("ix_work_assignments_user_id", "work_assignments", ["user_id"])
    op.create_index("ix_work_assignment_user_dates", "work_assignments", ["user_id", "start_date", "end_date"])

    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("hours_total", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        _fk_user("reviewed_by"), sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_note", sa.String(500)),
        _ts("created_at"), _ts("updated_at"),
        sa.UniqueConstraint("user_id", "report_date", name="uq_daily_report_user_date"),
    )
    op.create_index("ix_daily_reports_tenant_id", "daily_reports", ["tenant_id"])
    op.create_index("ix_daily_reports_user_id", "daily_reports", ["user_id"])
    op.create_index("ix_daily_report_tenant_date", "daily_reports", ["tenant_id", "report_date"])

    op.create_table(
        "daily_report_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("what", sa.String(500), nullable=False),
        sa.Column("hours", sa.Numeric(4, 2)),
        sa.Column("status", sa.String(12), nullable=False, server_default="done"),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("targets.id", ondelete="SET NULL")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_daily_report_lines_report_id", "daily_report_lines", ["report_id"])

    conn = op.get_bind()
    for code, description in PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (code, description, requires_step_up) "
                "VALUES (:c, :d, false) ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description"
            ),
            {"c": code, "d": description},
        )
    for role, perm in GRANTS:
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
    for code, _ in PERMISSIONS:
        conn.execute(sa.text(
            "DELETE FROM role_permissions WHERE permission_id = (SELECT id FROM permissions WHERE code = :p)"
        ), {"p": code})
        conn.execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": code})
    for table in ("daily_report_lines", "daily_reports", "work_assignments",
                  "target_updates", "target_milestones", "targets"):
        op.drop_table(table)
