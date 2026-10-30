"""Add settings.min_working_hours.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1

Every attendance screen displayed "minimum hours required" and every
compliance figure was calculated against it, but no such column existed. The
frontend filled the gap with its own hardcoded 9.0, so the number looked real,
agreed with itself everywhere, and could not be changed — the Settings page had
nowhere to save it.

server_default 9.0 matches the value the UI was already assuming, so existing
tenants see no behavioural change on upgrade; they simply gain the ability to
set it.
"""

from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
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
    _ensure_column(
        "settings",
        sa.Column(
            "min_working_hours",
            sa.Float(),
            nullable=False,
            server_default="9.0",
        ),
        fill_sql="9.0",
    )


def downgrade() -> None:
    op.drop_column("settings", "min_working_hours")
