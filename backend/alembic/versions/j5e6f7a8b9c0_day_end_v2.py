"""Day-end reporting v2: assigned work items, linked report lines, blockers.

Revision ID: j5e6f7a8b9c0
Revises: i4d5e6f7a8b9

work_assignments    a single "focus" becomes a work item: priority, due date,
                    status and % complete. It stays on the person's list
                    until done, so unfinished work carries over by itself.
daily_report_lines  a line can report on an assigned item or a Task Manager
                    task, with % complete and a note.
daily_reports       blockers, tomorrow's plan, late flag, the signed-in time
                    captured at submit, and who reopened it and why.

Focuses created before this migration were time-boxed (a day or a week).
Those whose window has already ended are closed as cancelled, so they do not
suddenly reappear as overdue work; the rest stay open with their window's end
as the due date.
"""

import sqlalchemy as sa

from alembic import op

revision = "j5e6f7a8b9c0"
down_revision = "i4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── work items ──────────────────────────────────────────────────────────
    op.add_column("work_assignments", sa.Column("priority", sa.String(8), nullable=False, server_default="medium"))
    op.add_column("work_assignments", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("work_assignments", sa.Column("status", sa.String(12), nullable=False, server_default="not_started"))
    op.add_column("work_assignments", sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("work_assignments", sa.Column("completed_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_work_assignment_status", "work_assignments",
        "status IN ('not_started','in_progress','blocked','done','cancelled')",
    )
    op.create_check_constraint(
        "ck_work_assignment_priority", "work_assignments",
        "priority IN ('low','medium','high','urgent')",
    )
    op.create_check_constraint(
        "ck_work_assignment_progress", "work_assignments", "progress BETWEEN 0 AND 100",
    )
    op.create_index("ix_work_assignment_user_status", "work_assignments", ["user_id", "status"])
    op.execute("UPDATE work_assignments SET due_date = end_date WHERE due_date IS NULL")
    op.execute("UPDATE work_assignments SET status = 'cancelled' WHERE end_date < CURRENT_DATE")

    # ─── report lines ────────────────────────────────────────────────────────
    op.add_column("daily_report_lines", sa.Column(
        "assignment_id", sa.Integer(), sa.ForeignKey("work_assignments.id", ondelete="SET NULL"), nullable=True))
    op.add_column("daily_report_lines", sa.Column(
        "task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True))
    op.add_column("daily_report_lines", sa.Column("progress", sa.Integer(), nullable=True))
    op.add_column("daily_report_lines", sa.Column("note", sa.String(500), nullable=True))
    op.create_index("ix_daily_report_lines_assignment_id", "daily_report_lines", ["assignment_id"])
    op.create_index("ix_daily_report_lines_task_id", "daily_report_lines", ["task_id"])

    # ─── reports ─────────────────────────────────────────────────────────────
    op.add_column("daily_reports", sa.Column("blockers", sa.Text(), nullable=True))
    op.add_column("daily_reports", sa.Column("tomorrow_plan", sa.Text(), nullable=True))
    op.add_column("daily_reports", sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("daily_reports", sa.Column("clock_seconds", sa.Integer(), nullable=True))
    op.add_column("daily_reports", sa.Column(
        "reopened_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("daily_reports", sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("daily_reports", sa.Column("reopen_note", sa.String(500), nullable=True))


def downgrade() -> None:
    for col in ("reopen_note", "reopened_at", "reopened_by", "clock_seconds", "is_late", "tomorrow_plan", "blockers"):
        op.drop_column("daily_reports", col)
    op.drop_index("ix_daily_report_lines_task_id", table_name="daily_report_lines")
    op.drop_index("ix_daily_report_lines_assignment_id", table_name="daily_report_lines")
    for col in ("note", "progress", "task_id", "assignment_id"):
        op.drop_column("daily_report_lines", col)
    op.drop_index("ix_work_assignment_user_status", table_name="work_assignments")
    for ck in ("ck_work_assignment_progress", "ck_work_assignment_priority", "ck_work_assignment_status"):
        op.drop_constraint(ck, "work_assignments", type_="check")
    for col in ("completed_on", "progress", "status", "due_date", "priority"):
        op.drop_column("work_assignments", col)
