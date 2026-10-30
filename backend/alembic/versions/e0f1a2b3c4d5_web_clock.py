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
    op.alter_column("attendance_logs", "finger_id", existing_type=sa.Integer(), nullable=True)
    _ensure_column(
        "attendance_logs",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="device"),
        fill_sql="'device'",
    )
    _ensure_column("attendance_logs", sa.Column("source_ip", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_attendance_user_time", "attendance_logs", ["tenant_id", "user_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_user_time", table_name="attendance_logs")
    op.execute("DELETE FROM attendance_logs WHERE finger_id IS NULL")
    op.drop_column("attendance_logs", "source_ip")
    op.drop_column("attendance_logs", "source")
    op.alter_column("attendance_logs", "finger_id", existing_type=sa.Integer(), nullable=False)
