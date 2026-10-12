"""Payroll management.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5

  pay_components          the organisation's earnings and deductions —
                          Basic, HRA, PF, ESI, PT ... nothing preloaded
  employee_pay_profiles   salary or stipend, PAN / UAN / ESIC / bank details
  salary_revisions        append-only salary structures: the revision history
  reimbursements          expense claims, paid with the next payroll
  payroll_runs            one month: draft -> submitted -> closed
  payroll_entries         one person's computed payslip in a run

Permissions
  payroll.view            read runs, registers and payslips
  payroll.manage          configure components, structures; prepare a month
  payroll.approve         approve and close a month (never one you submitted)
  reimbursement.approve   decide expense claims of people you administer

Granted to tenant_admin (all four) and org_admin (reimbursement.approve,
their own department only — enforced in the route). super_admin has
everything through grants_all.
"""

from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("payroll.view", "Read payroll runs, registers and payslips"),
    ("payroll.manage", "Configure pay components and salary structures; prepare a payroll month"),
    ("payroll.approve", "Approve and close a payroll month someone else submitted"),
    ("reimbursement.approve", "Approve or reject expense claims of people you administer"),
]
GRANTS = [
    ("tenant_admin", "payroll.view"),
    ("tenant_admin", "payroll.manage"),
    ("tenant_admin", "payroll.approve"),
    ("tenant_admin", "reimbursement.approve"),
    ("org_admin", "reimbursement.approve"),
]


def _ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "pay_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("calc", sa.String(16), nullable=False, server_default="fixed"),
        sa.Column("rate", sa.Numeric(7, 4)),
        sa.Column("employer_rate", sa.Numeric(7, 4)),
        sa.Column("base_codes", sa.String(255)),
        sa.Column("wage_ceiling", sa.Numeric(12, 2)),
        sa.Column("gross_limit", sa.Numeric(12, 2)),
        sa.Column("slabs", sa.JSON()),
        sa.Column("prorate", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("applies_to", sa.String(16), nullable=False, server_default="all"),
        sa.Column("is_statutory", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        _ts("created_at"), _ts("updated_at"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_pay_component_code"),
    )
    op.create_index("ix_pay_components_tenant_id", "pay_components", ["tenant_id"])

    op.create_table(
        "employee_pay_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("pay_type", sa.String(16), nullable=False, server_default="salary"),
        sa.Column("designation", sa.String(80)),
        sa.Column("date_of_joining", sa.Date()),
        sa.Column("pan", sa.String(10)),
        sa.Column("uan", sa.String(12)),
        sa.Column("pf_number", sa.String(32)),
        sa.Column("esic_number", sa.String(17)),
        sa.Column("pt_state", sa.String(40)),
        sa.Column("bank_name", sa.String(80)),
        sa.Column("bank_account", sa.String(34)),
        sa.Column("bank_ifsc", sa.String(11)),
        sa.Column("exempt_codes", sa.String(255)),
        _ts("updated_at"),
    )
    op.create_index("ix_employee_pay_profiles_tenant_id", "employee_pay_profiles", ["tenant_id"])

    op.create_table(
        "salary_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("annual_ctc", sa.Numeric(14, 2), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(255)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        _ts("created_at"),
    )
    op.create_index("ix_salary_rev_user_from", "salary_revisions", ["tenant_id", "user_id", "effective_from"])

    op.create_table(
        "payroll_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("prepared_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("returned_note", sa.String(500)),
        sa.Column("totals", sa.JSON()),
        _ts("created_at"), _ts("updated_at"),
        sa.UniqueConstraint("tenant_id", "period", name="uq_payroll_run_period"),
    )

    op.create_table(
        "payroll_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("lop_override", sa.Numeric(5, 2)),
        sa.Column("override_note", sa.String(255)),
        sa.Column("adjustments", sa.JSON()),
        sa.Column("gross", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_pay", sa.Numeric(14, 2), nullable=False, server_default="0"),
        _ts("created_at"), _ts("updated_at"),
        sa.UniqueConstraint("run_id", "user_id", name="uq_payroll_entry_person"),
    )
    op.create_index("ix_payroll_entries_run_id", "payroll_entries", ["run_id"])

    op.create_table(
        "reimbursements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(120)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.String(255)),
        sa.Column("payroll_run_id", sa.Integer(), sa.ForeignKey("payroll_runs.id", ondelete="SET NULL")),
        _ts("created_at"),
    )
    op.create_index("ix_reimb_tenant_status", "reimbursements", ["tenant_id", "status"])

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
    for code, _ in PERMISSIONS:
        conn.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id = (SELECT id FROM permissions WHERE code = :p)"
            ),
            {"p": code},
        )
        conn.execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": code})
    op.drop_table("reimbursements")
    op.drop_table("payroll_entries")
    op.drop_table("payroll_runs")
    op.drop_table("salary_revisions")
    op.drop_table("employee_pay_profiles")
    op.drop_table("pay_components")
