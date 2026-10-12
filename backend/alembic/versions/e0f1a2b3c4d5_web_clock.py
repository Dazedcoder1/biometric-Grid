"""Web sign-in clock.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4

Employees can now sign in and out from the browser as well as at a
fingerprint scanner. Both kinds of punch go into attendance_logs, so one day
is one list whichever way each punch was made.

  attendance_logs.finger_id   now NULLable — a web punch has no finger.
  attendance_logs.source      "device" | "web". Existing rows are all
                              scanner punches, so the default backfills them.
  attendance_logs.source_ip   where a web punch came from.
  ix_attendance_user_time     (tenant_id, user_id, timestamp) — every clock
                              query is "this person / these people, this day".

Downgrade deletes web punches first: they have no finger_id, and the column
cannot go back to NOT NULL while they exist.
"""

from alembic import op
import sqlalchemy as sa

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("attendance_logs", "finger_id", existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "attendance_logs",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="device"),
    )
    op.add_column("attendance_logs", sa.Column("source_ip", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_attendance_user_time", "attendance_logs", ["tenant_id", "user_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_user_time", table_name="attendance_logs")
    op.execute("DELETE FROM attendance_logs WHERE finger_id IS NULL")
    op.drop_column("attendance_logs", "source_ip")
    op.drop_column("attendance_logs", "source")
    op.alter_column("attendance_logs", "finger_id", existing_type=sa.Integer(), nullable=False)
